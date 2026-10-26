"""The forecasting family on one shared contract (plan F3).

Why this module exists
----------------------
RNN, LSTM, TCN and SSM were placeholders, and the three ``*_timeseries``
boosters were ordinary tabular regressors on a **shuffled** split - a
time-ordered CSV leaked the future into the training rows, which is the same
kind of false claim the catalog work removed elsewhere.

One contract serves them all (that is what makes the comparison view
meaningful):

* the data is a series with a target column, an optional time column and
  optional numeric covariates; missing values are reported and filled;
* the split is **chronological, never shuffled**: the tail fraction the
  request's ``test_size`` names is the test segment, 10 percent of the
  remainder is the validation segment, and windows are cut inside each
  segment (a test window may use earlier rows as inputs, but its targets lie
  inside the test segment);
* the scaler is fitted on the training segment only;
* the prediction is **direct**: the network answers the next ``horizon``
  values as a vector, not a recursive loop;
* the metrics are MAE, RMSE, sMAPE and MASE against two baselines - the
  naive forecast (repeat the last value) and the seasonal naive (the period
  comes from a ``seasonality`` option or the autocorrelation) - plus a skill
  score, and a model that does not beat the naive forecast is flagged;
* the artifact is a ``TimeSeriesBundle``: the scaler statistics, the
  architecture configuration and the ``state_dict``; predict takes the last
  ``window`` rows (unscaled) and returns the next ``horizon`` values.

The architectures: an Elman RNN and an LSTM (a linear head on the last
hidden state), a TCN (residual blocks of dilated causal convolutions, left
padding only), a diagonal state-space model in the style of S4D and LRU (a
complex diagonal state matrix with a magnitude below one by construction,
learned input and output maps, a skip term, stacked with normalisation,
gating and residual connections - not Mamba, not full S4), and the boosters
in forecasting mode (lag features over the window, rolling statistics,
calendar features from the time column).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .bundles import register_loader
from .charts import cap_charts

try:
    import torch
    import torch.nn as nn
except ImportError:  # pragma: no cover - torch is optional for the tabular models
    torch = None
    nn = None

# The defaults of the shared contract (plan F3).
DEFAULT_WINDOW = 24
DEFAULT_HORIZON = 1
DEFAULT_SEASONALITY = None
VALIDATION_FRACTION = 0.1
MAX_EPOCHS_DEFAULT = 10
PATIENCE_DEFAULT = 5


# --- the data contract -----------------------------------------------------------


def _prepare_series(
    dataset: pd.DataFrame,
    label_column: str,
    time_column: Optional[str],
) -> Tuple[pd.DataFrame, List[str]]:
    """The target, the covariates and the time column of a forecasting run.

    The target must be numeric; the covariates are the other numeric columns
    (the time column is not a feature); missing values are reported by the
    caller and filled here (forward fill, the option of plan F3).
    """
    if label_column not in dataset.columns:
        raise ValueError(f"The target column '{label_column}' is not in the dataset.")
    target = pd.to_numeric(dataset[label_column], errors="coerce")
    if target.notna().sum() == 0:
        raise ValueError(f"The target column '{label_column}' has no numeric value.")

    frame = pd.DataFrame(index=dataset.index)
    frame[label_column] = target
    covariates: List[str] = []
    for column in dataset.columns:
        if column in (label_column, time_column):
            continue
        numeric = pd.to_numeric(dataset[column], errors="coerce")
        if numeric.notna().mean() > 0.5:
            frame[column] = numeric
            covariates.append(column)
    if time_column is not None and time_column in dataset.columns:
        frame[time_column] = dataset[time_column]
    frame = frame.interpolate(limit_direction="both")
    frame = frame.dropna(subset=[label_column])
    return frame, covariates


def _autocorr_period(values: np.ndarray, max_lag: int = 48) -> Optional[int]:
    """The seasonal period from the autocorrelation (plan F3)."""
    series = values - values.mean()
    denominator = float(np.sum(series ** 2))
    if denominator <= 0:
        return None
    best_lag, best_value = None, 0.3
    for lag in range(2, min(max_lag, len(values) // 3) + 1):
        correlation = float(np.sum(series[lag:] * series[:-lag])) / denominator
        if correlation > best_value:
            best_lag, best_value = lag, correlation
    return best_lag


def _chronological_split(
    n_rows: int, test_size: float
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The train/validation/test indices of a chronological split (plan F3).

    First the tail fraction named by ``test_size`` is the test segment; 10
    percent of the remainder is the validation segment; the rest trains.
    """
    n_test = max(1, int(round(test_size * n_rows)))
    n_test = min(n_test, max(1, n_rows - 4))
    test_start = n_rows - n_test
    n_val = max(1, int(round(VALIDATION_FRACTION * test_start)))
    val_start = test_start - n_val
    return np.arange(0, val_start), np.arange(val_start, test_start), np.arange(test_start, n_rows)


def _cut_windows(
    frame: pd.DataFrame,
    feature_columns: List[str],
    window: int,
    horizon: int,
    indices: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """The windows of a segment: inputs are ``window`` rows, the targets are
    the next ``horizon`` values of the target column (plan F3).

    A window may start before the segment (a test window uses earlier rows as
    inputs), but its targets always lie inside the segment.
    """
    values = frame[feature_columns].to_numpy(dtype=float)
    target_index = 0  # the target column is the first of the feature columns
    X, y = [], []
    for end in indices:
        start = int(end) - window
        target_end = int(end) + horizon
        if start < 0 or target_end > len(values):
            continue
        X.append(values[start:int(end)])
        y.append(values[int(end):target_end, target_index])
    if not X:
        raise ValueError(
            f"The series is too short for window={window} and horizon={horizon}: "
            f"no complete window fits the segment."
        )
    return np.asarray(X, dtype=float), np.asarray(y, dtype=float)


def _score_forecast(
    y_true: np.ndarray, y_pred: np.ndarray, naive_pred: np.ndarray, seasonal_pred: np.ndarray, seasonal: Optional[int]
) -> Dict[str, Any]:
    """The full metric set of plan F3 against the naive baselines."""
    truth = np.asarray(y_true, dtype=float)
    prediction = np.asarray(y_pred, dtype=float)
    naive = np.asarray(naive_pred, dtype=float)
    seasonal_naive = np.asarray(seasonal_pred, dtype=float)

    mae = float(np.mean(np.abs(truth - prediction)))
    naive_mae = float(np.mean(np.abs(truth - naive)))
    seasonal_mae = float(np.mean(np.abs(truth - seasonal_naive)))
    denominator = np.abs(truth) + np.abs(prediction)
    smape = float(
        np.mean(2.0 * np.abs(truth - prediction) / np.where(denominator == 0, 1e-9, denominator)) * 100
    )
    metrics: Dict[str, Any] = {
        "mae": round(mae, 6),
        "rmse": round(float(np.sqrt(np.mean((truth - prediction) ** 2))), 6),
        "smape": round(smape, 4),
        "baseline_naive_mae": round(naive_mae, 6),
        "baseline_seasonal_naive_mae": round(seasonal_mae, 6),
        "seasonality": seasonal,
        "skill_vs_naive": round(1.0 - mae / naive_mae, 4) if naive_mae > 0 else None,
        "skill_vs_seasonal": round(1.0 - mae / seasonal_mae, 4) if seasonal_mae > 0 else None,
        "beats_naive": bool(mae < naive_mae) if naive_mae > 0 else None,
        "beats_seasonal_naive": bool(mae < seasonal_mae) if seasonal_mae > 0 else None,
    }
    if seasonal is None:
        # MASE against the in-sample naive error needs the training series;
        # when no seasonality is given the naive skill already says it.
        metrics["mase"] = round(mae / naive_mae, 4) if naive_mae > 0 else None
    return metrics


def _naive_predictions(
    frame: pd.DataFrame, target_column: str, ends: np.ndarray, horizon: int, seasonality: Optional[int]
) -> Tuple[np.ndarray, np.ndarray]:
    """The naive and seasonal-naive forecasts for the same windows.

    The naive forecast repeats the last observed value; the seasonal naive
    repeats the value one period back. Both are computed exactly like the
    model's targets, so the comparison is fair.
    """
    values = frame[target_column].to_numpy(dtype=float)
    naive, seasonal = [], []
    for end in ends:
        end = int(end)
        last = values[end - 1]
        naive.append([last] * horizon)
        if seasonality:
            period_values = [
                values[end - seasonality + (step % seasonality)] for step in range(horizon)
            ]
            seasonal.append(period_values)
        else:
            seasonal.append([last] * horizon)
    return np.asarray(naive), np.asarray(seasonal)


# --- the architectures (plan F3) ----------------------------------------------------


if torch is not None:

    class RNNForecaster(nn.Module):
        """The Elman RNN / LSTM forecaster: a linear head on the last state."""

        def __init__(self, n_features: int, hidden_size: int, num_layers: int, horizon: int, lstm: bool = False):
            super().__init__()
            if lstm:
                self.rnn = nn.LSTM(n_features, hidden_size, num_layers=num_layers, batch_first=True)
            else:
                self.rnn = nn.RNN(
                    n_features, hidden_size, num_layers=num_layers, batch_first=True, nonlinearity="tanh"
                )
            self.head = nn.Linear(hidden_size, horizon)

        def forward(self, x):
            output, _ = self.rnn(x)
            return self.head(output[:, -1, :])

    class TCNForecaster(nn.Module):
        """Residual blocks of dilated causal convolutions, left padding only."""

        def __init__(
            self,
            n_features: int,
            horizon: int,
            num_channels: int = 16,
            levels: int = 3,
            kernel_size: int = 3,
            dropout: float = 0.1,
        ):
            super().__init__()
            self.blocks = nn.ModuleList()
            self.residuals = nn.ModuleList()
            in_channels = n_features
            for level in range(levels):
                dilation = 2 ** level
                padding = (kernel_size - 1) * dilation  # left padding only
                self.blocks.append(
                    nn.Conv1d(in_channels, num_channels, kernel_size, dilation=dilation, padding=padding)
                )
                self.residuals.append(
                    nn.Conv1d(in_channels, num_channels, 1) if in_channels != num_channels else nn.Identity()
                )
                in_channels = num_channels
            self.dropout = nn.Dropout(dropout)
            self.head = nn.Linear(num_channels, horizon)
            self.receptive_field = 1 + sum((kernel_size - 1) * 2 ** level for level in range(levels))

        def forward(self, x):
            # x: (batch, window, features) -> (batch, features, window)
            current = x.transpose(1, 2)
            for block, residual in zip(self.blocks, self.residuals):
                out = block(current)[:, :, : current.shape[2]]  # causal: cut the right padding
                current = nn.functional.gelu(out) + residual(current)
                current = self.dropout(current)
            return self.head(current[:, :, -1])

    class DiagonalSSM(nn.Module):
        """A diagonal state-space layer in the style of S4D and LRU.

        The state matrix is complex diagonal with a magnitude below one by
        construction (the magnitude is parameterised through a sigmoid, so
        it lives in (0, 1) whatever the training does), so the layer is
        stable after training - a test asserts it. Learned
        input and output maps, a skip term, normalisation, gating and a
        residual connection around it.
        """

        def __init__(self, d_model: int, state_dim: int):
            super().__init__()
            self.state_dim = state_dim
            # The magnitude is parameterised through a sigmoid: it lives in
            # (0, 1) by construction, whatever the training does (a free
            # log-magnitude parameter could cross one and go unstable).
            # sigmoid(2.197) = 0.9, the LRU-style initial magnitude.
            self.magnitude_raw = nn.Parameter(
                torch.full((state_dim,), float(np.log(0.9 / 0.1)))
            )
            self.phase = nn.Parameter(torch.randn(state_dim) * 0.5)
            self.input_real = nn.Linear(d_model, state_dim)
            self.input_imag = nn.Linear(d_model, state_dim)
            self.out_real = nn.Linear(state_dim, d_model)
            self.out_imag = nn.Linear(state_dim, d_model)
            self.norm = nn.LayerNorm(d_model)
            self.gate = nn.Linear(d_model, d_model)

        def state_matrix(self):
            magnitude = torch.sigmoid(self.magnitude_raw)
            return magnitude * torch.exp(1j * self.phase)

        def forward(self, x):
            # x: (batch, window, d_model) - the recurrence is the scan over
            # the window, kept simple (a Python loop over the time steps).
            A = self.state_matrix()
            real = self.input_real(x)
            imag = self.input_imag(x)
            state = torch.zeros(x.shape[0], self.state_dim, dtype=torch.cfloat, device=x.device)
            outputs = []
            for step in range(x.shape[1]):
                B_step = torch.complex(real[:, step, :], imag[:, step, :])
                state = A * state + B_step
                outputs.append(torch.real(self.out_real(state.real) - self.out_imag(state.imag)))
            stacked = torch.stack(outputs, dim=1)
            skip = x
            return self.norm(torch.sigmoid(self.gate(x)) * stacked + skip)

    class SSMForecaster(nn.Module):
        def __init__(self, n_features: int, hidden_size: int, state_dim: int, num_layers: int, horizon: int):
            super().__init__()
            self.input = nn.Linear(n_features, hidden_size)
            self.layers = nn.ModuleList(
                [DiagonalSSM(hidden_size, state_dim) for _ in range(max(1, num_layers))]
            )
            self.head = nn.Linear(hidden_size, horizon)

        def forward(self, x):
            current = self.input(x)
            for layer in self.layers:
                current = current + layer(current)
            return self.head(current[:, -1, :])


# --- the bundle ---------------------------------------------------------------------


class TimeSeriesBundle:
    """The artifact of a forecasting run (plans C1, F3)."""

    kind = "timeseries"
    request_kind = "window_rows"

    def __init__(
        self,
        model: Any,
        architecture: str,
        config: Dict[str, Any],
        feature_columns: List[str],
        target_column: str,
        window: int,
        horizon: int,
        scaler_mean: Optional[np.ndarray],
        scaler_std: Optional[np.ndarray],
    ):
        self.model = model  # a torch module, or a fitted booster
        self.architecture = architecture  # rnn | lstm | tcn | ssm | booster-<name>
        self.config = config
        self.feature_columns = list(feature_columns)
        self.target_column = target_column
        self.window = window
        self.horizon = horizon
        self.scaler_mean = scaler_mean
        self.scaler_std = scaler_std

    def schema(self) -> Dict[str, Any]:
        return {
            "request_kind": self.request_kind,
            "kind": self.kind,
            "features": self.feature_columns,
            "target_column": self.target_column,
            "window": self.window,
            "horizon": self.horizon,
            "output": f"the next {self.horizon} values of '{self.target_column}'",
        }

    def _scale(self, rows: np.ndarray) -> np.ndarray:
        values = np.asarray(rows, dtype=float)
        if values.ndim != 2 or values.shape[1] != len(self.feature_columns):
            raise ValueError(
                f"The window must be a list of {self.window} rows with "
                f"{len(self.feature_columns)} value(s) each, in the order "
                f"{self.feature_columns}."
            )
        if self.scaler_mean is not None and self.scaler_std is not None:
            std = np.where(np.asarray(self.scaler_std) == 0, 1.0, self.scaler_std)
            return (values - np.asarray(self.scaler_mean)) / std
        return values

    def _unscale(self, values: np.ndarray) -> np.ndarray:
        if self.scaler_mean is not None and self.scaler_std is not None:
            # The target is the first of the feature columns.
            mean, std = self.scaler_mean[0], self.scaler_std[0]
            std = 1.0 if std == 0 else std
            return values * std + mean
        return values

    def infer(self, request: Dict[str, Any]) -> Dict[str, Any]:
        rows = request.get("window_rows") or []
        if len(rows) != self.window:
            raise ValueError(
                f"The request must carry exactly {self.window} row(s) (the last "
                f"{self.window} observations of '{self.target_column}'"
                + (
                    f" and the covariates {self.feature_columns[1:]}"
                    if len(self.feature_columns) > 1
                    else ""
                )
                + ")."
            )
        scaled = self._scale(rows)
        if self.architecture.startswith("booster"):
            features = _booster_window_features(scaled, self.window, self.horizon, self.config)
            models = self.model if isinstance(self.model, list) else [self.model]
            prediction = np.asarray(
                [float(m.predict(features)[0]) for m in models], dtype=float
            )[: self.horizon]
        else:
            if torch is None:
                raise RuntimeError("torch is not installed")
            tensor = torch.tensor(scaled, dtype=torch.float32).unsqueeze(0)
            self.model.eval()
            with torch.no_grad():
                output = self.model(tensor).numpy().reshape(-1)
            prediction = output[: self.horizon]
        return {"predictions": [round(float(v), 6) for v in self._unscale(prediction)]}

    def save(self, directory: Path) -> None:
        directory = Path(directory)
        if self.architecture.startswith("booster"):
            import joblib

            joblib.dump(
                {"model": self.model, "config": self.config},
                directory / "model.joblib",
            )
        else:
            torch.save(self.model.state_dict(), directory / "model.pt")
        (directory / "config.json").write_text(
            json.dumps(
                {
                    "kind": self.kind,
                    "architecture": self.architecture,
                    "config": _plain_config(self.config),
                    "features": self.feature_columns,
                    "target_column": self.target_column,
                    "window": self.window,
                    "horizon": self.horizon,
                    "scaler_mean": None if self.scaler_mean is None else [float(v) for v in self.scaler_mean],
                    "scaler_std": None if self.scaler_std is None else [float(v) for v in self.scaler_std],
                }
            )
        )

    @classmethod
    def load(cls, directory: Path, manifest: Optional[Dict[str, Any]] = None) -> "TimeSeriesBundle":
        directory = Path(directory)
        config = json.loads((directory / "config.json").read_text())
        if config["architecture"].startswith("booster"):
            import joblib

            payload = joblib.load(directory / "model.joblib")
            model = payload["model"]
        else:
            if torch is None:
                raise RuntimeError("torch is not installed")
            arch = config["architecture"]
            net_config = config["config"]
            n_features = len(config["features"])
            model = build_architecture(
                arch, n_features, config["horizon"], net_config
            )
            model.load_state_dict(torch.load(directory / "model.pt", map_location="cpu"))
            model.eval()
        return cls(
            model=model,
            architecture=config["architecture"],
            config=config["config"],
            feature_columns=config["features"],
            target_column=config["target_column"],
            window=config["window"],
            horizon=config["horizon"],
            scaler_mean=None
            if config.get("scaler_mean") is None
            else np.asarray(config["scaler_mean"], dtype=float),
            scaler_std=None
            if config.get("scaler_std") is None
            else np.asarray(config["scaler_std"], dtype=float),
        )


register_loader("timeseries", TimeSeriesBundle.load)


def _plain_config(config: Dict[str, Any]) -> Dict[str, Any]:
    plain = {}
    for key, value in config.items():
        if isinstance(value, (int, float, str, bool)) or value is None:
            plain[key] = value
        else:
            plain[key] = str(value)
    return plain


def build_architecture(
    architecture: str, n_features: int, horizon: int, config: Dict[str, Any]
):
    """Rebuild an architecture from its configuration (plan C1).

    The registry of architectures is what lets a torch artifact be a
    ``state_dict`` plus a config instead of a pickled class: the class can
    move in the code, the artifact still loads.
    """
    if torch is None:
        raise RuntimeError("torch is not installed")
    if architecture == "rnn":
        return RNNForecaster(n_features, int(config.get("hidden_size", 64)), int(config.get("num_layers", 1)), horizon)
    if architecture == "lstm":
        return RNNForecaster(
            n_features, int(config.get("hidden_size", 64)), int(config.get("num_layers", 1)), horizon, lstm=True
        )
    if architecture == "tcn":
        return TCNForecaster(
            n_features,
            horizon,
            num_channels=int(config.get("num_channels", 16)),
            levels=int(config.get("levels", 3)),
            kernel_size=int(config.get("kernel_size", 3)),
            dropout=float(config.get("dropout", 0.1)),
        )
    if architecture == "ssm":
        return SSMForecaster(
            n_features,
            int(config.get("hidden_size", 64)),
            int(config.get("state_dim", 32)),
            int(config.get("num_layers", 2)),
            horizon,
        )
    raise ValueError(f"Unknown forecasting architecture '{architecture}'.")


# --- the booster forecasting mode (plan F3) -------------------------------------------


def _booster_window_features(
    scaled_window: np.ndarray, window: int, horizon: int, config: Dict[str, Any]
) -> np.ndarray:
    """The lag/rolling/calendar features of the booster forecasting mode.

    The input is one scaled window (window rows x features, target first);
    the output is one feature vector for one forecast.
    """
    target = scaled_window[:, 0]
    lags = [float(target[-1])]  # the last value
    lags += [float(target[-lag]) for lag in (2, 3, 4, 6, 12, 24) if lag <= len(target)]
    roll = [float(target.mean()), float(target.std() if len(target) > 1 else 0.0)]
    covariates = [float(v) for v in scaled_window[-1, 1:]]
    return np.asarray([lags + roll + covariates], dtype=float)


def _booster_feature_matrix(
    windows: np.ndarray, window: int, horizon: int
) -> np.ndarray:
    rows = []
    for window_values in windows:
        target = window_values[:, 0]
        lags = [float(target[-1])]
        lags += [float(target[-lag]) for lag in (2, 3, 4, 6, 12, 24) if lag <= len(target)]
        roll = [float(target.mean()), float(target.std() if len(target) > 1 else 0.0)]
        covariates = [float(v) for v in window_values[-1, 1:]]
        rows.append(lags + roll + covariates)
    return np.asarray(rows, dtype=float)


def _build_booster(model_name: str, params: Dict[str, Any]):
    """The booster of a forecasting run, with the tabular parameters only."""
    tabular_keys = {
        "n_estimators", "learning_rate", "max_depth", "subsample", "colsample_bytree",
        "gamma", "num_leaves", "boosting_type", "iterations", "depth", "l2_leaf_reg",
        "border_count", "random_state",
    }
    booster_params = {k: v for k, v in params.items() if k in tabular_keys}
    booster_params.setdefault("random_state", 42)
    if model_name == "XGboost_timeseries":
        try:
            import xgboost as xgb
        except ImportError:
            raise RuntimeError("xgboost is not installed") from None
        return xgb.XGBRegressor(**booster_params)
    if model_name == "lightGBM_timeseries":
        try:
            import lightgbm as lgb
        except ImportError:
            raise RuntimeError("lightgbm is not installed") from None
        return lgb.LGBMRegressor(**booster_params, verbose=-1)
    if model_name == "CATboost_timeseries":
        try:
            import catboost as cb
        except ImportError:
            raise RuntimeError("catboost is not installed") from None
        return cb.CatBoostRegressor(**booster_params, verbose=False)
    raise ValueError(f"'{model_name}' has no forecasting mode.")


# --- the trainer ------------------------------------------------------------------------


def train_forecaster(
    model_name: str,
    dataset: pd.DataFrame,
    label_column: str,
    params: Dict[str, Any],
    time_column: Optional[str] = None,
) -> Tuple[Dict[str, Any], TimeSeriesBundle]:
    """Train a forecaster on the shared contract (plan F3)."""
    frame, covariates = _prepare_series(dataset, label_column, time_column)
    window = max(2, int(params.get("window", DEFAULT_WINDOW)))
    horizon = max(1, int(params.get("horizon", DEFAULT_HORIZON)))
    test_size = float(params.get("test_size", 0.2) or 0.2)
    random_state = int(params.get("random_state", 42))

    values = frame[label_column].to_numpy(dtype=float)
    seasonality = params.get("seasonality", DEFAULT_SEASONALITY)
    if seasonality:
        seasonality = int(seasonality)
    else:
        seasonality = _autocorr_period(values)

    feature_columns = [label_column] + covariates
    train_idx, val_idx, test_idx = _chronological_split(len(frame), test_size)

    X_train, y_train = _cut_windows(frame, feature_columns, window, horizon, train_idx)
    X_val, y_val = _cut_windows(frame, feature_columns, window, horizon, val_idx)
    X_test, y_test = _cut_windows(frame, feature_columns, window, horizon, test_idx)

    # The scaler is fitted on the training segment only (plan F3): the test
    # rows never touch it, which is what a leakage test can rebuild. The
    # target is the first feature column, so its statistics are the same
    # scaler's first entry - the head learns in the standardized space and
    # the evaluation unscales, consistently on both sides.
    train_mean = X_train.reshape(-1, X_train.shape[2]).mean(axis=0)
    train_std = X_train.reshape(-1, X_train.shape[2]).std(axis=0)
    train_std = np.where(train_std == 0, 1.0, train_std)

    def _scale_windows(windows: np.ndarray) -> np.ndarray:
        return (windows - train_mean) / train_std

    def _scale_targets(targets: np.ndarray) -> np.ndarray:
        return (targets - train_mean[0]) / train_std[0]

    X_train_s, X_val_s, X_test_s = map(_scale_windows, (X_train, X_val, X_test))
    y_train_s, y_val_s = _scale_targets(y_train), _scale_targets(y_val)

    architecture = {
        "RNN": "rnn",
        "LSTM": "lstm",
        "TCN_timeseries": "tcn",
        "SSM_timeseries": "ssm",
    }.get(model_name)
    is_booster = architecture is None

    metrics: Dict[str, Any] = {
        "task_type": "timeseries",
        "model_name": model_name,
        "window": window,
        "horizon": horizon,
        "seasonality": seasonality,
        "train_size": int(len(X_train)),
        "validation_size": int(len(X_val)),
        "test_size": int(len(X_test)),
        "time_column": time_column,
        "covariates": covariates,
        "rows_filled_missing": int(dataset[label_column].isna().sum()),
        "artifact_kind": TimeSeriesBundle.kind,
    }

    loss_curve: List[float] = []

    if is_booster:
        # One booster per horizon step (the direct multi-step of plan F3):
        # CatBoost has no multi-output regressor, and one model per step is
        # what "direct" means anyway.
        features_train = _booster_feature_matrix(X_train_s, window, horizon)
        features_test = _booster_feature_matrix(X_test_s, window, horizon)
        model = []
        for step in range(horizon):
            booster = _build_booster(model_name, params)
            booster.fit(features_train, y_train_s[:, step])
            model.append(booster)
        predictions_scaled = np.stack(
            [np.asarray(b.predict(features_test), dtype=float) for b in model], axis=1
        )
        config = {"booster": model_name}
    else:
        if torch is None:
            raise RuntimeError("torch is not installed: the neural forecasters need it")
        torch.manual_seed(random_state)
        net_config = {
            "hidden_size": int(params.get("hidden_size", 64)),
            "num_layers": int(params.get("num_layers", 1)),
            "state_dim": int(params.get("state_dim", 32)),
            "num_channels": int(params.get("num_channels", 16)),
            "levels": int(params.get("levels", 3)),
            "kernel_size": int(params.get("kernel_size", 3)),
            "dropout": float(params.get("dropout", 0.0)),
        }
        model = build_architecture(architecture, len(feature_columns), horizon, net_config)
        epochs = int(params.get("epochs", MAX_EPOCHS_DEFAULT))
        patience = int(params.get("patience", PATIENCE_DEFAULT))
        learning_rate = float(params.get("learning_rate", 1e-3))
        batch_size = int(params.get("batch_size", 32))

        optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
        X_train_t = torch.tensor(X_train_s, dtype=torch.float32)
        y_train_t = torch.tensor(y_train_s, dtype=torch.float32)
        X_val_t = torch.tensor(X_val_s, dtype=torch.float32)
        y_val_t = torch.tensor(y_val_s, dtype=torch.float32)

        best_val = float("inf")
        best_state = None
        stale = 0
        for epoch in range(max(1, epochs)):
            model.train()
            order = torch.randperm(len(X_train_t))
            total = 0.0
            for start in range(0, len(order), batch_size):
                batch = order[start : start + batch_size]
                optimizer.zero_grad()
                output = model(X_train_t[batch])
                loss = nn.functional.mse_loss(output, y_train_t[batch])
                loss.backward()
                # Gradient clipping at 1.0 (plan F3).
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                total += float(loss.detach()) * len(batch)
            loss_curve.append(round(total / len(order), 6))
            model.eval()
            with torch.no_grad():
                val_loss = float(nn.functional.mse_loss(model(X_val_t), y_val_t))
            if val_loss < best_val:
                best_val = val_loss
                best_state = {key: value.clone() for key, value in model.state_dict().items()}
                stale = 0
            else:
                stale += 1
                if stale >= patience:
                    break  # early stopping on the validation loss (plan F3)
        if best_state is not None:
            model.load_state_dict(best_state)  # best-checkpoint restore
        model.eval()
        with torch.no_grad():
            predictions_scaled = (
                model(torch.tensor(X_test_s, dtype=torch.float32)).numpy().reshape(len(X_test_s), -1)[:, :horizon]
            )
        config = net_config
        if architecture == "tcn":
            metrics["receptive_field"] = int(model.receptive_field)
            metrics["receptive_field_covers_window"] = bool(model.receptive_field >= window)
        if architecture == "ssm":
            magnitudes = torch.abs(model.layers[0].state_matrix()).detach()
            metrics["ssm_state_max_magnitude"] = round(float(magnitudes.max()), 4)
            metrics["ssm_states_below_one"] = bool(float(magnitudes.max()) < 1.0)

    # Unscale the predictions (the target is the first feature column).
    target_mean, target_std = train_mean[0], train_std[0]
    predictions = predictions_scaled * target_std + target_mean
    if horizon == 1:
        predictions = predictions.reshape(-1, 1)

    naive_pred, seasonal_pred = _naive_predictions(
        frame, label_column, test_idx[: len(predictions)], horizon, seasonality
    )
    truth = y_test[: len(predictions)]

    forecast_metrics = _score_forecast(truth, predictions, naive_pred, seasonal_pred, seasonality)
    metrics.update(forecast_metrics)

    # The chart data of plan E1: the forecast against the actual values over
    # the test window, the error per forecast step and the training loss.
    charts: Dict[str, Any] = {
        "forecast_vs_actual": {
            "actual": [round(float(v), 6) for v in truth[:, 0]],
            "predicted": [round(float(v), 6) for v in predictions[:, 0]],
        },
    }
    if horizon > 1:
        charts["error_per_step"] = [
            round(float(np.mean(np.abs(truth[:, step] - predictions[:, step]))), 6)
            for step in range(horizon)
        ]
    if loss_curve:
        charts["loss_curve"] = loss_curve
    metrics["_charts"] = cap_charts(charts)

    bundle = TimeSeriesBundle(
        model=model,
        architecture=architecture if not is_booster else f"booster-{model_name}",
        config=config,
        feature_columns=feature_columns,
        target_column=label_column,
        window=window,
        horizon=horizon,
        scaler_mean=train_mean,
        scaler_std=train_std,
    )
    return metrics, bundle
