import copy
import json
import os
import re
import uuid
import random
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sklearn.neural_network import MLPRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.base import clone
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder
import warnings
import joblib
import numpy as np
import pandas as pd
from datasets import load_dataset
from sklearn.cluster import AgglomerativeClustering, KMeans, DBSCAN
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.mixture import GaussianMixture
from sklearn.metrics import accuracy_score, mean_squared_error, r2_score, silhouette_score
from sklearn.model_selection import RandomizedSearchCV, train_test_split
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.svm import SVC, SVR

try:
    from hmmlearn import hmm
except ImportError:
    hmm = None

try:
    import xgboost as xgb
except ImportError:
    xgb = None

try:
    import lightgbm as lgb
except ImportError:
    lgb = None

try:
    import catboost as cb
except ImportError:
    cb = None

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, Dataset
except ImportError:
    torch = None
    nn = None
    DataLoader = None
    Dataset = None

try:
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        TrainingArguments,
        Trainer,
        set_seed,
    )
except ImportError:
    AutoModelForSequenceClassification = None
    AutoTokenizer = None
    TrainingArguments = None
    Trainer = None
    set_seed = None

try:
    import gymnasium as gym
except ImportError:
    gym = None

try:
    import umap
except ImportError:
    umap = None

try:
    import hdbscan
except ImportError:
    hdbscan = None

try:
    from stable_baselines3 import DQN, PPO
except ImportError:
    DQN = None
    PPO = None

try:
    import torchvision
    from torchvision import transforms
    from torchvision.datasets import ImageFolder
    from torchvision.models import resnet18, resnet50
except ImportError:
    torchvision = None
    transforms = None
    ImageFolder = None
    resnet18 = None
    resnet50 = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from . import clustering as clustering_module
from . import forecasting as forecasting_module
from . import graph_models as graph_module
from . import rl as rl_module
from . import textmodels as text_module
from . import vision as vision_module
from .bundles import write_bundle
from .charts import (
    build_classification_charts,
    build_regression_charts,
    cap_charts,
    cv_fold_chart,
    permutation_importances,
)
from .tabular import (
    SCALE_SENSITIVE_MODELS,
    AutoencoderBundle,
    FeaturePlan,
    FeatureInputError,
    TabularModelBundle,
    analyze_features,
    build_preprocessor,
    coerce_features,
    cross_validate_pipeline,
    describe_features,
    evaluate_holdout,
    parse_preprocessing_options,
    parse_split_options,
    preprocessing_report,
    split_data,
)


def find_repo_root() -> Path:
    candidate = Path(__file__).resolve()
    for _ in range(6):
        if (candidate / "ML_models").exists() or (candidate / "backend").exists() or (candidate / "data").exists():
            return candidate
        if candidate.parent == candidate:
            break
        candidate = candidate.parent
    return Path(__file__).resolve().parents[2]

ROOT = find_repo_root()
MODEL_DIR = ROOT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Parameters that belong to the training loop instead of the estimator: they configure the
# train/test split and are passed to train_test_split() separately. They are stripped from
# the client-supplied hyperparameters in train_model() (so no estimator can ever receive
# them) and again in build_model() / _train_clustering() as defence in depth. Unknown
# parameter names are deliberately NOT filtered - a typo must still raise TypeError from
# the constructor.
# The keys of the shared forecasting contract (plan F3): they configure the
# training loop, never an estimator constructor. Without them here, a
# catalog entry that carries "forecasting" or "window" would hand them to
# CatBoostClassifier.
_TRAINER_OWNED_PARAMS = {
    "test_size",
    "forecasting",
    "window",
    "horizon",
    "seasonality",
    "patience",
    "time_column",
}

# Keys that only one branch of a shared catalog entry accepts: SVC has "probability" and
# "random_state", SVR has neither. A catalog entry shared by two estimators can only hold
# the intersection of their parameters, so these are set or dropped per branch in
# build_model() and are never taken from the catalog.
_BRANCH_SPECIFIC_PARAMS = {"probability", "random_state"}

MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "K-Mean": {
        "category": "clustering",
        "description": "K-Means clustering on tabular data.",
        "params": {"n_clusters": 8, "random_state": 42},
        "optimization": ["n_clusters"],
        "implemented": True,
        "test_results": {
            "expected_silhouette": (0.40, 0.80),
            "best_for": ["customer_segmentation", "data_exploration", "large_scale_clustering"],
            "typical_training_time_sec": 2,
            "scalability": "high",
        },
    },
    "HMM_timeseries": {
        # Category "clustering" routes the model to _train_clustering(), which owns the
        # GaussianHMM branch. The former "time-series" category fell through to the
        # tabular flow and died with "Unsupported model: HMM_timeseries".
        "category": "clustering",
        "description": "HMM-based time-series modeling.",
        "params": {"n_components": 4, "covariance_type": "diag", "n_iter": 100},
        "optimization": ["n_components"],
        "implemented": True,
        "test_results": {
            "expected_accuracy": (0.65, 0.85),
            "best_for": ["sequence_prediction", "behavior_analysis", "signal_detection"],
            "typical_training_time_sec": 5,
            "scalability": "medium",
        },
    },
    "GMM": {
        "category": "clustering",
        "description": "Gaussian mixture modeling for clustering.",
        "params": {"n_components": 3, "covariance_type": "full", "random_state": 42},
        "optimization": ["n_components"],
        "implemented": True,
        "test_results": {
            "expected_silhouette": (0.35, 0.75),
            "best_for": ["probabilistic_clustering", "mixture_modeling"],
            "typical_training_time_sec": 3,
            "scalability": "medium",
        },
    },
    "Hierarchical_Clustering": {
        "category": "clustering",
        "description": "Agglomerative hierarchical clustering.",
        "params": {"n_clusters": 4, "linkage": "ward"},
        "optimization": ["n_clusters"],
        "implemented": True,
        "test_results": {
            "expected_silhouette": (0.30, 0.70),
            "best_for": ["dendrogram_analysis", "small_to_medium_datasets"],
            "typical_training_time_sec": 8,
            "scalability": "low",
        },
    },
    "PCA": {
        "category": "clustering",
        "description": "Principal Component Analysis for dimensionality reduction (often used before clustering).",
        "params": {"n_components": 2, "svd_solver": "auto", "random_state": 42},
        "optimization": ["n_components"],
        "implemented": True,
        "test_results": {
            "expected_explained_variance": (0.5, 0.95),
            "best_for": ["dimensionality_reduction", "visualization", "preprocessing"],
            "typical_training_time_sec": 1,
            "scalability": "high",
        },
    },
    "t-SNE": {
        "category": "clustering",
        "description": "t-distributed Stochastic Neighbor Embedding for visualization and embedding.",
        "params": {"n_components": 2, "perplexity": 30.0, "learning_rate": 200.0, "random_state": 42},
        "optimization": ["n_components", "perplexity"],
        "implemented": True,
        "test_results": {
            "expected_quality": (0.4, 0.9),
            "best_for": ["visualization", "small_datasets", "embedding"],
            "typical_training_time_sec": 3,
            "scalability": "low",
        },
    },
    "UMAP": {
        "category": "clustering",
        "description": "UMAP for fast dimensionality reduction and visualization.",
        "params": {"n_components": 2, "n_neighbors": 15, "min_dist": 0.1, "random_state": 42},
        "optimization": ["n_components", "n_neighbors"],
        "implemented": True,
        "test_results": {
            "expected_quality": (0.45, 0.92),
            "best_for": ["visualization", "embedding", "preprocessing"],
            "typical_training_time_sec": 2,
            "scalability": "high",
        },
    },
    "DBSCAN": {
        "category": "clustering",
        "description": "Density-based clustering using DBSCAN.",
        "params": {"eps": 0.5, "min_samples": 5, "metric": "euclidean"},
        "optimization": ["eps", "min_samples"],
        "implemented": True,
        "test_results": {
            "expected_silhouette": (0.2, 0.75),
            "best_for": ["noise_detection", "arbitrary_shape_clusters", "spatial_data"],
            "typical_training_time_sec": 2,
            "scalability": "medium",
        },
    },
    "HDBSCAN": {
        "category": "clustering",
        "description": "Hierarchical density-based clustering (HDBSCAN).",
        "params": {"min_cluster_size": 5, "min_samples": None},
        "optimization": ["min_cluster_size", "min_samples"],
        "implemented": True,
        "test_results": {
            "expected_quality": (0.3, 0.9),
            "best_for": ["robust_density_clustering", "variable_density"],
            "typical_training_time_sec": 4,
            "scalability": "medium",
        },
    },
    "Random_Forest": {
        "category": "classification",
        "description": "Random Forest classifier for tabular data.",
        "params": {
            "n_estimators": 100,
            "max_depth": None,
            "min_samples_split": 2,
            "min_samples_leaf": 1,
            "random_state": 42,
            "n_jobs": -1,
        },
        "search_space": {
            "n_estimators": [50, 100, 200],
            "max_depth": [None, 5, 10, 20],
            "min_samples_split": [2, 5, 10],
            "min_samples_leaf": [1, 2, 4],
        },
        "optimization": ["n_estimators", "max_depth", "min_samples_split", "min_samples_leaf"],
        "implemented": True,
        "test_results": {
            "expected_accuracy": (0.75, 0.95),
            "best_for": ["tabular_classification", "feature_importance", "mixed_feature_types"],
            "typical_training_time_sec": 3,
            "scalability": "high",
        },
    },
    "Logistic_Regression": {
        "category": "classification",
        "description": "Logistic Regression classifier.",
        "params": {
            "C": 1.0,
            "max_iter": 1000,
            "solver": "lbfgs",
            "penalty": "l2",
            "random_state": 42,
        },
        "search_space": {
            "C": [0.1, 1.0, 10.0],
            "max_iter": [100, 1000, 3000],
            "solver": ['lbfgs', 'liblinear'],
            "penalty": ['l2'],
        },
        "optimization": ["C", "penalty"],
        "implemented": True,
        "test_results": {
            "expected_accuracy": (0.70, 0.90),
            "best_for": ["linear_separable_data", "probability_calibration", "interpretability"],
            "typical_training_time_sec": 1,
            "scalability": "high",
        },
    },
    "MLR": {
        "category": "regression",
        "description": "Multiple Linear Regression for numeric prediction.",
        "params": {"fit_intercept": True},
        "search_space": {
            "fit_intercept": [True, False],
        },
        "optimization": ["fit_intercept"],
        "implemented": True,
        "test_results": {
            "expected_r2": (0.60, 0.95),
            "best_for": ["linear_regression", "coefficient_analysis", "small_datasets"],
            "typical_training_time_sec": 0.5,
            "scalability": "high",
        },
    },
    "KNN": {
        "category": "classification",
        "description": "K-Nearest Neighbors for classification or regression.",
        "params": {
            "n_neighbors": 5,
            "weights": "uniform",
            "algorithm": "auto",
            "p": 2,
            "n_jobs": -1,
        },
        "search_space": {
            "n_neighbors": [3, 5, 7, 9],
            "weights": ['uniform', 'distance'],
            "algorithm": ['auto', 'ball_tree', 'kd_tree', 'brute'],
            "p": [1, 2],
        },
        "optimization": ["n_neighbors", "p"],
        "implemented": True,
        "test_results": {
            "expected_accuracy": (0.65, 0.90),
            "best_for": ["non_linear_boundaries", "small_to_medium_datasets"],
            "typical_training_time_sec": 0.1,
            "scalability": "medium",
        },
    },
    "SVM": {
        "category": "classification",
        "description": "Support Vector Machine for classification or regression.",
        # The entry feeds both SVC (classification) and SVR (regression): only keys that
        # both estimators accept belong here - SVR has no "probability" and, since
        # scikit-learn 1.9, no "random_state".
        "params": {
            "C": 1.0,
            "kernel": "rbf",
            "gamma": "scale",
            "tol": 1e-3,
        },
        "search_space": {
            "C": [0.1, 1.0, 10.0],
            "kernel": ['rbf', 'linear', 'poly'],
            "gamma": ['scale', 'auto'],
            "tol": [0.001],
        },
        "optimization": ["C", "kernel", "gamma"],
        "implemented": True,
        "test_results": {
            "expected_accuracy": (0.75, 0.95),
            "best_for": ["high_dimensional_data", "binary_classification", "kernel_methods"],
            "typical_training_time_sec": 4,
            "scalability": "medium",
        },
    },
    "XGboost_timeseries": {
        "category": "time-series",
        "description": (
            "XGBoost for tabular regression. In forecasting mode "
            "(hyperparameter forecasting=true) it uses the shared time-series "
            "contract: lag features over the window, rolling statistics, a "
            "chronological split and the naive baselines. Without that mode it "
            "is an ordinary tabular regressor on a shuffled split, which is what "
            "the old name hid."
        ),
        "params": {
            "n_estimators": 100,
            "learning_rate": 0.1,
            "max_depth": 6,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "gamma": 0,
            "forecasting": False,
            "window": 24,
            "horizon": 1,
            "random_state": 42,
        },
        "search_space": {
            "n_estimators": [50, 100, 200],
            "learning_rate": [0.01, 0.1, 0.2],
            "max_depth": [3, 6, 9],
            "subsample": [0.6, 0.8, 1.0],
            "colsample_bytree": [0.6, 0.8, 1.0],
            "gamma": [0, 0.1, 0.2],
        },
        "optimization": ["n_estimators", "learning_rate", "max_depth"],
        "implemented": True,
        "dataset_kind": "tabular",
        "bundle_kind": "tabular",
        "requires_gpu": False,
        "min_memory_mb": 512,
        "downloads_checkpoint": False,
        "test_results": {
            "expected_accuracy": (0.80, 0.95),
            "best_for": ["gradient_boosting", "feature_interactions", "forecasting_baseline"],
            "typical_training_time_sec": 6,
            "scalability": "high",
        },
    },
    "lightGBM_timeseries": {
        "category": "time-series",
        "description": (
            "LightGBM for fast tabular training. In forecasting mode "
            "(hyperparameter forecasting=true) it uses the shared time-series "
            "contract with lag features and a chronological split, next to the "
            "naive baselines. On small series the boosters often beat the neural "
            "networks, which is why they are the honest baseline family."
        ),
        "params": {
            "boosting_type": "gbdt",
            "n_estimators": 100,
            "learning_rate": 0.1,
            "num_leaves": 31,
            "subsample": 0.8,
            "max_depth": -1,
            "forecasting": False,
            "window": 24,
            "horizon": 1,
            "random_state": 42,
        },
        "search_space": {
            "n_estimators": [50, 100, 200],
            "learning_rate": [0.01, 0.1, 0.2],
            "num_leaves": [15, 31, 63],
            "subsample": [0.6, 0.8, 1.0],
            "max_depth": [-1, 3, 6],
        },
        "optimization": ["n_estimators", "learning_rate", "num_leaves"],
        "implemented": True,
        "dataset_kind": "tabular",
        "bundle_kind": "tabular",
        "requires_gpu": False,
        "min_memory_mb": 512,
        "downloads_checkpoint": False,
        "test_results": {
            "expected_accuracy": (0.80, 0.96),
            "best_for": ["fast_training", "large_datasets", "memory_efficient"],
            "typical_training_time_sec": 3,
            "scalability": "high",
        },
    },
    "CATboost_timeseries": {
        "category": "time-series",
        "description": (
            "CatBoost for robust tabular training. In forecasting mode "
            "(hyperparameter forecasting=true) it uses the shared time-series "
            "contract with lag features and a chronological split, next to the "
            "naive baselines."
        ),
        "params": {
            "iterations": 100,
            "learning_rate": 0.1,
            "depth": 6,
            "l2_leaf_reg": 3,
            "border_count": 32,
            "forecasting": False,
            "window": 24,
            "horizon": 1,
            "random_state": 42,
        },
        "search_space": {
            "iterations": [50, 100, 200],
            "learning_rate": [0.01, 0.1, 0.2],
            "depth": [3, 6, 9],
            "l2_leaf_reg": [1, 3, 5],
            "border_count": [32, 64, 128],
        },
        "optimization": ["iterations", "learning_rate", "depth"],
        "implemented": True,
        "dataset_kind": "tabular",
        "bundle_kind": "tabular",
        "requires_gpu": False,
        "min_memory_mb": 512,
        "downloads_checkpoint": False,
        "test_results": {
            "expected_accuracy": (0.78, 0.94),
            "best_for": ["categorical_features", "robustness", "automatic_feature_interaction"],
            "typical_training_time_sec": 7,
            "scalability": "high",
        },
    },
    "PPO": {
        "category": "reinforcement-learning",
        "description": "Proximal Policy Optimization for RL environments.",
        "params": {
            "learning_rate": 2.5e-4,
            "n_steps": 2048,
            "batch_size": 64,
            "gamma": 0.99,
            "ent_coef": 0.01,
            "training_steps": 10000,
        },
        "optimization": ["learning_rate", "n_steps"],
        "implemented": True,
        "test_results": {
            "expected_reward": (100, 500),
            "best_for": ["continuous_control", "policy_optimization", "sample_efficiency"],
            "typical_training_time_sec": 15,
            "scalability": "medium",
        },
    },
    "DQN": {
        "category": "reinforcement-learning",
        "description": "Deep Q-network for discrete action spaces.",
        "params": {
            "learning_rate": 1e-4,
            "buffer_size": 100000,
            "learning_starts": 1000,
            "gamma": 0.99,
            "training_steps": 10000,
        },
        "optimization": ["learning_rate", "buffer_size"],
        "implemented": True,
        "test_results": {
            "expected_reward": (50, 300),
            "best_for": ["discrete_actions", "experience_replay", "exploration"],
            "typical_training_time_sec": 20,
            "scalability": "medium",
        },
    },
    "Q-Learning": {
        "category": "reinforcement-learning",
        "description": (
            "Tabular Q-learning, the textbook algorithm, for environments with a "
            "discrete state and action space (FrozenLake, Taxi, CliffWalking, "
            "Blackjack). Evaluated on fresh episodes with fixed seeds next to a "
            "uniformly random policy."
        ),
        "params": {
            "learning_rate": 0.1,
            "discount_factor": 0.99,
            "epsilon": 1.0,
            "epsilon_min": 0.05,
            "epsilon_decay": 0.9995,
            "training_steps": 10000,
            "random_state": 42,
        },
        "optimization": ["learning_rate", "discount_factor"],
        "implemented": True,
        "dataset_kind": "environment",
        "bundle_kind": "q_table",
        "requires_gpu": False,
        "min_memory_mb": 256,
        "downloads_checkpoint": False,
        "test_results": {
            "expected_reward": (30, 200),
            "best_for": ["tabular_environments", "simple_mdp", "convergence_guarantee"],
            "typical_training_time_sec": 10,
            "scalability": "low",
        },
    },
    "Autoencoder": {
        "category": "autoencoder",
        "description": (
            "Autoencoder: a network that learns to reproduce its own standardised input "
            "through a narrow bottleneck. It reports the reconstruction error against a "
            "predict-the-mean baseline, flags unusual rows (anomaly detection) and returns "
            "the bottleneck code of a row."
        ),
        "params": {
            "latent_dim": 4,
            "hidden_units": 16,
            "activation": "relu",
            "epochs": 200,
            "batch_size": 32,
            "learning_rate": 0.001,
            "weight_decay": 0.0001,
            "anomaly_quantile": 0.95,
        },
        "optimization": ["latent_dim", "learning_rate"],
        "implemented": True,
        "test_results": {
            # The error is measured on standardised features, where 1.0 is what
            # predicting the mean of every column scores.
            "expected_reconstruction_mse": (0.0, 1.0),
            "best_for": ["dimensionality_reduction", "anomaly_detection", "feature_extraction"],
            "typical_training_time_sec": 2,
            "scalability": "medium",
        },
    },
    "BERT2BERT": {
        "category": "nlp",
        "task": "seq2seq",
        "description": (
            "An EncoderDecoderModel warm-started from two BERT checkpoints, "
            "fine-tuned on source and target columns with ROUGE-1/2/L and exact "
            "match against the copy-the-source baseline. It learns its "
            "cross-attention from scratch, so it is weaker than T5 on small "
            "data; a GPU is recommended for anything real."
        ),
        "params": {
            "epochs": 1,
            "batch_size": 8,
            "learning_rate": 2e-5,
            "max_length": 128,
            "model_name": "bert-base-uncased",
        },
        "optimization": ["learning_rate"],
        "implemented": True,
        "dataset_kind": "text_pairs",
        "bundle_kind": "text_seq2seq",
        "requires_gpu": "recommended",
        "min_memory_mb": 4096,
        "downloads_checkpoint": True,
        "allowed_checkpoints": ["bert-base-uncased"],
        "test_results": {
            "best_for": ["seq2seq_tasks", "encoder_decoder_pretraining"],
            "typical_training_time_sec": 30,
            "scalability": "medium",
        },
    },
    "self-attenetion_transformer": {
        "category": "nlp",
        "task": "classification",
        "description": (
            "DistilBERT text classification (the entry name is a historical "
            "alias; the architecture is DistilBERT, a distilled BERT with the "
            "same attention mechanism). Measured on a stratified held-out split: "
            "accuracy, macro F1 and the majority baseline, with the truncation "
            "rate of max_length."
        ),
        "params": {
            "epochs": 1,
            "batch_size": 8,
            "learning_rate": 2e-5,
            "max_length": 128,
            "model_name": "distilbert-base-uncased",
        },
        "optimization": ["learning_rate"],
        "implemented": True,
        "dataset_kind": "text",
        "bundle_kind": "text_classifier",
        "requires_gpu": False,
        "min_memory_mb": 2048,
        "downloads_checkpoint": True,
        "allowed_checkpoints": ["distilbert-base-uncased"],
        "test_results": {
            "expected_accuracy": (0.85, 0.95),
            "best_for": ["text_classification", "attention_mechanisms", "efficient_models"],
            "typical_training_time_sec": 25,
            "scalability": "high",
        },
    },
    "seq2seq": {
        "category": "nlp",
        "task": "seq2seq",
        "description": (
            "Sequence-to-sequence fine-tuning of t5-small on source and target "
            "columns: held-out loss, ROUGE-1/2/L and exact match, against the "
            "copy-the-source and first-sentence baselines. Generation uses beam "
            "search (default 4)."
        ),
        "params": {
            "epochs": 1,
            "batch_size": 8,
            "learning_rate": 2e-5,
            "max_length": 128,
            "task_prefix": "",
            "model_name": "t5-small",
        },
        "optimization": ["learning_rate"],
        "implemented": True,
        "dataset_kind": "text_pairs",
        "bundle_kind": "text_seq2seq",
        "requires_gpu": False,
        "min_memory_mb": 2048,
        "downloads_checkpoint": True,
        "allowed_checkpoints": ["t5-small"],
        "test_results": {
            "best_for": ["translation", "summarization", "paraphrase_generation"],
            "typical_training_time_sec": 35,
            "scalability": "medium",
        },
    },
    "UL2": {
        "category": "nlp",
        "description": (
            "Retired: the UL2 checkpoint has 20 billion parameters (about 40 GB "
            "in half precision before any training state), and no hardware this "
            "product targets can train or serve it. Renaming a small T5 as "
            "UL2-style would claim a thing it is not, which is the dishonesty "
            "the catalog work removed. Hidden by default; revisit only with a "
            "worker that has two 80 GB GPUs."
        ),
        "params": {},
        "optimization": [],
        "implemented": False,
        "not_supported": (
            "20 billion parameters cannot be trained or served on the hardware "
            "this product targets (about 40 GB of weights in half precision)."
        ),
        "hidden": True,
        "dataset_kind": "text",
        "bundle_kind": None,
        "requires_gpu": True,
        "min_memory_mb": 80000,
        "downloads_checkpoint": True,
    },
    "GNN": {
        "category": "graph",
        "description": (
            "Semi-supervised node classification with a two-layer graph "
            "convolutional network over a sparse, symmetrically normalised "
            "adjacency with self-loops (no PyTorch Geometric). The metrics sit "
            "next to a majority baseline and a feature-only MLP baseline, which "
            "is the honest test of whether the graph helps. Full-batch."
        ),
        "params": {
            "epochs": 200,
            "hidden_size": 32,
            "layer": "gcn",
            "dropout": 0.5,
            "weight_decay": 0.0005,
            "learning_rate": 0.01,
            "symmetrise": True,
            "random_state": 42,
        },
        "optimization": ["hidden_size", "learning_rate"],
        "implemented": True,
        "dataset_kind": "graph",
        "bundle_kind": "graph",
        "requires_gpu": False,
        "min_memory_mb": 1024,
        "downloads_checkpoint": False,
        "test_results": {
            "expected_accuracy": (0.75, 0.92),
            "best_for": ["node_classification", "graph_learning", "semi_supervised"],
            "typical_training_time_sec": 20,
            "scalability": "medium",
        },
    },
    "BERT": {
        "category": "nlp",
        "task": "classification",
        "description": (
            "BERT text classification, measured on a stratified held-out split: "
            "accuracy, macro F1 and the majority baseline, with the truncation "
            "rate of max_length."
        ),
        "params": {
            "epochs": 1,
            "batch_size": 16,
            "learning_rate": 2e-5,
            "weight_decay": 0.01,
            "max_length": 128,
            "model_name": "bert-base-uncased",
        },
        "optimization": ["learning_rate", "weight_decay"],
        "implemented": True,
        "dataset_kind": "text",
        "bundle_kind": "text_classifier",
        "requires_gpu": False,
        "min_memory_mb": 2048,
        "downloads_checkpoint": True,
        "allowed_checkpoints": ["bert-base-uncased"],
        "test_results": {
            "expected_accuracy": (0.88, 0.96),
            "best_for": ["text_classification", "sentiment_analysis", "nli_tasks"],
            "typical_training_time_sec": 28,
            "scalability": "high",
        },
    },
    "DistilBERT": {
        "category": "nlp",
        "task": "classification",
        "description": (
            "DistilBERT text classification, measured on a stratified held-out "
            "split: accuracy, macro F1 and the majority baseline."
        ),
        "params": {
            "epochs": 1,
            "batch_size": 16,
            "learning_rate": 2e-5,
            "weight_decay": 0.01,
            "max_length": 128,
            "model_name": "distilbert-base-uncased",
        },
        "optimization": ["learning_rate", "weight_decay"],
        "implemented": True,
        "dataset_kind": "text",
        "bundle_kind": "text_classifier",
        "requires_gpu": False,
        "min_memory_mb": 2048,
        "downloads_checkpoint": True,
        "allowed_checkpoints": ["distilbert-base-uncased"],
        "test_results": {
            "expected_accuracy": (0.85, 0.94),
            "best_for": ["lightweight_models", "mobile_deployment", "fast_inference"],
            "typical_training_time_sec": 18,
            "scalability": "high",
        },
    },
    "GPT": {
        "category": "nlp",
        "task": "generation",
        "description": (
            "Causal language-model fine-tuning of distilgpt2 (gpt2 is also "
            "allow-listed): the text is packed into blocks of block_size tokens "
            "and the model learns to continue them. The report has the held-out "
            "cross-entropy and perplexity, the perplexity of the pretrained "
            "model before the fine-tuning (so the gain is visible) and a "
            "unigram baseline. Training is capped by max_train_tokens. This is "
            "generation, not classification."
        ),
        "params": {
            "epochs": 1,
            "batch_size": 4,
            "learning_rate": 2e-5,
            "block_size": 128,
            "max_train_tokens": 200000,
            "model_name": "distilgpt2",
        },
        "optimization": ["learning_rate"],
        "implemented": True,
        "dataset_kind": "text",
        "bundle_kind": "text_generation",
        "requires_gpu": False,
        "min_memory_mb": 2048,
        "downloads_checkpoint": True,
        "allowed_checkpoints": ["distilgpt2", "gpt2"],
        "test_results": {
            "best_for": ["text_generation", "language_modeling", "autoregressive_tasks"],
            "typical_training_time_sec": 25,
            "scalability": "high",
        },
    },
    "LLaMA": {
        "category": "nlp",
        "task": "generation",
        "description": (
            "LoRA fine-tuning of a Llama-architecture checkpoint from an "
            "allow-list: TinyLlama-1.1B-Chat (ungated, fits a 12 GB GPU) by "
            "default; the 7B model only when an administrator sets a Hugging "
            "Face token and accepts the licence. The artifact is the adapter "
            "(a few megabytes) plus the base model id, which keeps the storage "
            "quota small. 4-bit loading exists only on CUDA. Requires a GPU "
            "worker; on a CPU-only deployment this entry is unavailable and "
            "says why."
        ),
        "params": {
            "epochs": 1,
            "batch_size": 2,
            "learning_rate": 0.0002,
            "r": 8,
            "alpha": 16,
            "lora_dropout": 0.05,
            "block_size": 128,
            "max_train_tokens": 100000,
            "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        },
        "optimization": ["learning_rate", "r"],
        "implemented": True,
        "dataset_kind": "text",
        "bundle_kind": "text_generation",
        "requires_gpu": True,
        "min_memory_mb": 12000,
        "downloads_checkpoint": True,
        "allowed_checkpoints": ["TinyLlama/TinyLlama-1.1B-Chat-v1.0"],
        "test_results": {
            "best_for": ["instruction_following", "dialogue", "adapter_finetuning"],
            "typical_training_time_sec": 60,
            "scalability": "medium",
        },
    },
    "LSTM": {
        "category": "timeseries",
        "description": (
            "LSTM forecaster on the shared time-series contract: a chronological "
            "split (never shuffled), direct multi-step prediction, MAE/RMSE/sMAPE/"
            "MASE next to the naive and seasonal-naive baselines. A model that "
            "does not beat the naive forecast is flagged."
        ),
        "params": {
            "window": 24,
            "horizon": 1,
            "hidden_size": 64,
            "num_layers": 1,
            "dropout": 0.0,
            "epochs": 10,
            "batch_size": 32,
            "learning_rate": 0.001,
            "patience": 5,
            "random_state": 42,
        },
        "optimization": ["hidden_size", "learning_rate"],
        "implemented": True,
        "dataset_kind": "timeseries",
        "bundle_kind": "timeseries",
        "requires_gpu": False,
        "min_memory_mb": 1024,
        "downloads_checkpoint": False,
        "test_results": {
            "expected_mae_skill": (0.0, 1.0),
            "best_for": ["time_series", "sequence_modeling", "long_dependencies"],
            "typical_training_time_sec": 18,
            "scalability": "medium",
        },
    },
    "MiniLM": {
        "category": "nlp",
        "task": "classification",
        "description": (
            "MiniLM text classification, measured on a stratified held-out split: "
            "accuracy, macro F1 and the majority baseline."
        ),
        "params": {
            "epochs": 1,
            "batch_size": 16,
            "learning_rate": 2e-5,
            "weight_decay": 0.01,
            "max_length": 128,
            "model_name": "sentence-transformers/all-MiniLM-L6-v2",
        },
        "optimization": ["learning_rate", "weight_decay"],
        "implemented": True,
        "dataset_kind": "text",
        "bundle_kind": "text_classifier",
        "requires_gpu": False,
        "min_memory_mb": 2048,
        "downloads_checkpoint": True,
        "allowed_checkpoints": ["sentence-transformers/all-MiniLM-L6-v2"],
        "test_results": {
            "expected_accuracy": (0.82, 0.93),
            "best_for": ["semantic_similarity", "embedding_tasks", "fast_models"],
            "typical_training_time_sec": 15,
            "scalability": "high",
        },
    },
    "ResNet": {
        "category": "vision",
        "description": "ResNet image classifier (default ResNet-18).",
        "params": {
            "epochs": 3,
            "batch_size": 16,
            "learning_rate": 1e-3,
            "weight_decay": 1e-4,
            "optimizer": "adam",
            "momentum": 0.9,
            "pretrained": True,
            "trainable_layers": "all",
            "model_name": "resnet18",
        },
        "optimization": ["learning_rate", "weight_decay", "optimizer"],
        "implemented": True,
        "test_results": {
            "expected_accuracy": (0.85, 0.97),
            "best_for": ["image_classification", "transfer_learning", "object_recognition"],
            "typical_training_time_sec": 22,
            "scalability": "high",
        },
    },
    "ResNet50": {
        "category": "vision",
        "description": "ResNet-50 image classifier with optional torchvision support.",
        "params": {
            "epochs": 3,
            "batch_size": 16,
            "learning_rate": 1e-3,
            "weight_decay": 1e-4,
            "optimizer": "adam",
            "momentum": 0.9,
            "pretrained": True,
            "trainable_layers": "all",
            "model_name": "resnet50",
        },
        "optimization": ["learning_rate", "weight_decay", "optimizer"],
        "implemented": True,
        "test_results": {
            "expected_accuracy": (0.87, 0.98),
            "best_for": ["high_resolution_images", "fine_grained_classification", "production_systems"],
            "typical_training_time_sec": 35,
            "scalability": "high",
        },
    },
    "RNN": {
        "category": "timeseries",
        "description": (
            "Elman RNN (tanh) forecaster on the shared time-series contract: a "
            "chronological split, direct multi-step prediction and the naive "
            "baselines, so the number means what it says."
        ),
        "params": {
            "window": 24,
            "horizon": 1,
            "hidden_size": 64,
            "num_layers": 1,
            "dropout": 0.0,
            "epochs": 10,
            "batch_size": 32,
            "learning_rate": 0.001,
            "patience": 5,
            "random_state": 42,
        },
        "optimization": ["hidden_size", "learning_rate"],
        "implemented": True,
        "dataset_kind": "timeseries",
        "bundle_kind": "timeseries",
        "requires_gpu": False,
        "min_memory_mb": 1024,
        "downloads_checkpoint": False,
        "test_results": {
            "expected_mae_skill": (0.0, 1.0),
            "best_for": ["sequential_data", "basic_recurrence", "educational_purposes"],
            "typical_training_time_sec": 15,
            "scalability": "medium",
        },
    },
    "SSM_timeseries": {
        "category": "timeseries",
        "description": (
            "A diagonal state-space forecaster in the style of S4D and LRU: a "
            "complex diagonal state matrix with a magnitude below one (kept "
            "below one by construction), learned input and output maps, a skip "
            "term, stacked with normalisation, gating and residual connections. "
            "Not Mamba, and not full S4 - a diagonal SSM on the shared "
            "forecasting contract."
        ),
        "params": {
            "window": 24,
            "horizon": 1,
            "hidden_size": 64,
            "state_dim": 32,
            "num_layers": 2,
            "epochs": 10,
            "batch_size": 32,
            "learning_rate": 0.001,
            "patience": 5,
            "random_state": 42,
        },
        "optimization": ["hidden_size"],
        "implemented": True,
        "dataset_kind": "timeseries",
        "bundle_kind": "timeseries",
        "requires_gpu": False,
        "min_memory_mb": 1024,
        "downloads_checkpoint": False,
        "test_results": {
            "expected_mae_skill": (0.0, 1.0),
            "best_for": ["structured_state_modeling", "efficient_sequences", "long_range"],
            "typical_training_time_sec": 16,
            "scalability": "high",
        },
    },
    "TCN_timeseries": {
        "category": "timeseries",
        "description": (
            "Temporal convolutional forecaster: a stack of residual blocks of "
            "dilated causal one-dimensional convolutions (left padding only, "
            "the dilation doubling per level). The trainer checks that the "
            "receptive field covers the window and reports it. Shared "
            "forecasting contract with the naive baselines."
        ),
        "params": {
            "window": 24,
            "horizon": 1,
            "num_channels": 16,
            "levels": 3,
            "kernel_size": 3,
            "dropout": 0.1,
            "epochs": 10,
            "batch_size": 32,
            "learning_rate": 0.001,
            "patience": 5,
            "random_state": 42,
        },
        "optimization": ["num_channels", "learning_rate"],
        "implemented": True,
        "dataset_kind": "timeseries",
        "bundle_kind": "timeseries",
        "requires_gpu": False,
        "min_memory_mb": 1024,
        "downloads_checkpoint": False,
        "test_results": {
            "expected_mae_skill": (0.0, 1.0),
            "best_for": ["temporal_patterns", "parallel_processing", "long_sequences"],
            "typical_training_time_sec": 17,
            "scalability": "high",
        },
    },
    "ViT": {
        "category": "vision",
        "description": (
            "Vision Transformer image classification from the allow-listed "
            "checkpoint google/vit-base-patch16-224 with a new head. Linear "
            "probe by default (freeze_backbone=true); unfreezing the last "
            "blocks needs a GPU. On a CPU worker only the linear-probe mode is "
            "offered, and only up to 2000 images."
        ),
        "params": {
            "epochs": 3,
            "batch_size": 16,
            "learning_rate": 0.0001,
            "freeze_backbone": True,
            "image_size": 224,
            "model_name": "google/vit-base-patch16-224",
        },
        "optimization": ["learning_rate"],
        "implemented": True,
        "dataset_kind": "image_folder",
        "bundle_kind": "vision",
        "requires_gpu": "recommended",
        "min_memory_mb": 4096,
        "downloads_checkpoint": True,
        "allowed_checkpoints": ["google/vit-base-patch16-224"],
        "test_results": {
            "expected_accuracy": (0.86, 0.96),
            "best_for": ["modern_architectures", "attention_based_vision", "large_scale_data"],
            "typical_training_time_sec": 40,
            "scalability": "high",
        },
    },
}

ALIASES = {
    "K_Mean": "K-Mean",
    "Q_Learning": "Q-Learning",
    "Self_Attention_Transformer": "self-attenetion_transformer",
    "Self-Attention-Transformer": "self-attenetion_transformer",
    "Self_Attention": "self-attenetion_transformer",
    "Autoencoder": "Autoencoder",
    "BERT2BERT": "BERT2BERT",
    "Seq2Seq": "seq2seq",
    "GMM": "GMM",
    "HMM_timeseries": "HMM_timeseries",
    "Hierarchical_Clustering": "Hierarchical_Clustering",
    "PCA": "PCA",
    "TSNE": "t-SNE",
    "t_SNE": "t-SNE",
    "t-Sne": "t-SNE",
    "UMAP": "UMAP",
    "DBSCAN": "DBSCAN",
    "HDBSCAN": "HDBSCAN",
    "SSM_timeseries": "SSM_timeseries",
    "TCN_timeseries": "TCN_timeseries",
}

TRAINING_MODES = ["manual", "auto_tune", "auto_fine_tune", "llm_fine_tune", "auto_search"]

TRAINING_PRESETS = {
    "conservative": {
        "description": "Low learning rate, high regularization, fewer iterations",
        "adjustments": {
            "learning_rate": lambda x: x * 0.1 if isinstance(x, (int, float)) else x,
            "weight_decay": lambda x: x * 10 if isinstance(x, (int, float)) else x,
            "epochs": lambda x: max(1, int(x * 0.5)) if isinstance(x, (int, float)) else x,
            "n_estimators": lambda x: max(10, int(x * 0.7)) if isinstance(x, (int, float)) else x,
        },
    },
    "balanced": {
        "description": "Default settings optimized for most use cases",
        "adjustments": {},
    },
    "aggressive": {
        "description": "High learning rate, low regularization, more iterations",
        "adjustments": {
            "learning_rate": lambda x: x * 2 if isinstance(x, (int, float)) else x,
            "weight_decay": lambda x: x * 0.1 if isinstance(x, (int, float)) else x,
            "epochs": lambda x: int(x * 2) if isinstance(x, (int, float)) else x,
            "n_estimators": lambda x: int(x * 1.5) if isinstance(x, (int, float)) else x,
        },
    },
}


def apply_preset(hyperparameters: Dict[str, Any], preset_name: str) -> Dict[str, Any]:
    """Apply preset configuration adjustments to hyperparameters."""
    if preset_name not in TRAINING_PRESETS:
        return hyperparameters
    
    if preset_name == "balanced":
        return hyperparameters
    
    preset = TRAINING_PRESETS[preset_name]
    adjusted = copy.deepcopy(hyperparameters)
    
    for param_name, adjustment_func in preset["adjustments"].items():
        if param_name in adjusted:
            try:
                adjusted[param_name] = adjustment_func(adjusted[param_name])
            except (TypeError, ValueError):
                pass
    
    return adjusted


def normalize_model_name(name: str) -> str:
    if name in MODEL_CATALOG:
        return name
    if name in ALIASES:
        return ALIASES[name]
    cleaned = name.replace(" ", "_").replace("-", "_")
    if cleaned in ALIASES:
        return ALIASES[cleaned]
    if cleaned in MODEL_CATALOG:
        return cleaned
    return name


# What a catalog entry declares about its needs (plan F0/F8). The defaults are
# the values of a plain tabular model; an entry that needs more says so
# explicitly. "implemented" (the code exists and is tested) is separate from
# "available" (this deployment has the packages and the hardware), and the
# interface shows the reason an unavailable model is disabled.
_DECLARED_NEEDS_DEFAULTS = {
    "requires_gpu": False,
    "min_memory_mb": None,
    "downloads_checkpoint": False,
    "allowed_checkpoints": [],
    "dataset_kind": "tabular",
    "bundle_kind": None,
    "task": "classification",
    "hidden": False,
}

# Which category needs which optional package: the availability check of F8.
_CATEGORY_REQUIREMENTS = {
    "vision": ("torchvision", "Vision models need torch and torchvision."),
    "timeseries": ("torch", "The neural forecasters need torch."),
    "graph": ("torch", "The graph models need torch."),
    "nlp": ("transformers", "The text models need transformers and torch."),
}


def _package_installed(name: str) -> bool:
    import importlib

    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def model_availability(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Whether this deployment can run an entry, and why not (plan F8).

    "implemented" says the code exists and is tested; "available" says this
    deployment has the packages and the hardware. A GPU is only "recommended"
    for some entries (ViT, BERT2BERT): they run on CPU within the documented
    limits. An entry whose ``requires_gpu`` is True (LLaMA) is unavailable on
    a CPU-only worker, and the interface says why instead of queueing it
    forever.
    """
    if not entry.get("implemented", True):
        reason = entry.get("not_supported") or "this model is not implemented yet"
        return {"available": False, "reason": reason}
    category = entry.get("category", "custom")
    requirement = _CATEGORY_REQUIREMENTS.get(category)
    if requirement and not _package_installed(requirement[0]):
        return {"available": False, "reason": requirement[1]}
    if category == "reinforcement-learning" and not _package_installed("gymnasium"):
        return {"available": False, "reason": "The reinforcement-learning models need gymnasium."}
    requires_gpu = entry.get("requires_gpu", False)
    if requires_gpu is True:
        try:
            import torch

            if not torch.cuda.is_available():
                return {
                    "available": False,
                    "reason": "This model needs a GPU worker; this deployment has none.",
                }
        except ImportError:
            return {"available": False, "reason": "This model needs torch and a GPU worker."}
    return {"available": True, "reason": None}


def get_model_entry(model_name: str) -> Dict[str, Any]:
    normalized = normalize_model_name(model_name)
    if normalized in MODEL_CATALOG:
        entry = copy.deepcopy(MODEL_CATALOG[normalized])
        # Every implemented entry declares what it needs (plan F0): the
        # defaults below are what a plain tabular model needs, so an entry
        # that needs more has to say so explicitly.
        for key, default in _DECLARED_NEEDS_DEFAULTS.items():
            entry.setdefault(key, default)
        return entry
    return {
        "category": "custom",
        "description": "A model available in the repository.",
        "params": {},
        "optimization": [],
        **copy.deepcopy(_DECLARED_NEEDS_DEFAULTS),
    }


def list_available_models() -> List[Dict[str, Any]]:
    """The catalog, with the computed availability of every entry (plan F8).

    ``implemented`` says the code exists and is tested; ``available`` says
    this deployment has the packages and the hardware, and ``reason`` says
    why not when it does not. The hidden entries (the retired UL2) are not
    listed.
    """
    listed = []
    directories = [ROOT / "ML_models", ROOT / "DL_models", ROOT / "Encoder_Decoder"]
    seen = set()
    names: List[str] = []
    for directory in directories:
        if directory.exists():
            for file in sorted(directory.iterdir()):
                if file.suffix == ".py":
                    normalized = normalize_model_name(file.stem)
                    if normalized not in seen:
                        seen.add(normalized)
                        names.append(normalized)
    if not names:
        names = list(MODEL_CATALOG.keys())
    for normalized in names:
        if normalized not in MODEL_CATALOG:
            continue
        info = get_model_entry(normalized)
        if info.get("hidden"):
            continue
        availability = model_availability(info)
        listed.append({
            "name": normalized,
            "description": info.get("description", "Available model from repository."),
            "parameters": info.get("params", {}),
            "category": info.get("category", "custom"),
            "optimization": info.get("optimization", []),
            "test_results": info.get("test_results", {}),
            "planned_test_results": info.get("planned_test_results", {}),
            "implemented": info.get("implemented", True),
            "available": availability["available"],
            "unavailable_reason": availability["reason"],
            "requires_gpu": info.get("requires_gpu", False),
            "min_memory_mb": info.get("min_memory_mb"),
            "downloads_checkpoint": info.get("downloads_checkpoint", False),
            "dataset_kind": info.get("dataset_kind", "tabular"),
            "bundle_kind": info.get("bundle_kind"),
            "task": info.get("task", "classification"),
            "supported": True,
        })
    return listed


def list_model_categories() -> List[str]:
    return sorted({entry.get("category", "custom") for entry in MODEL_CATALOG.values()})


def parse_hugging_face_reference(value: str) -> str:
    if value.startswith("https://huggingface.co/datasets/"):
        return value.split("https://huggingface.co/datasets/", 1)[1]
    if value.startswith("https://www.huggingface.co/datasets/"):
        return value.split("https://www.huggingface.co/datasets/", 1)[1]
    return value


# A hub dataset identifier: ``name`` or ``owner/name``, the characters the hub
# itself allows. Everything else - an arbitrary URL, a local path, a scheme
# the datasets library happens to support (``csv://``, ``hf://``), a relative
# path that climbs out - is refused. This is the G3 fix: ``load_dataset`` with
# a client-supplied string must never become "the server fetches whatever this
# string points at".
_HF_DATASET_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}(/[A-Za-z0-9][A-Za-z0-9._-]{0,127})?$"
)


def validate_hf_dataset_reference(value: str) -> str:
    """Return the hub identifier, or raise ``ValueError`` with the reason.

    Accepts a hub identifier (``squad``, ``owner/name``) or a hub *dataset*
    URL (``https://huggingface.co/datasets/owner/name``), which is reduced to
    its identifier first. A file path, an arbitrary URL, a repository id with
    a revision pin (``owner/name@rev``) or anything else is refused.
    """
    if value is None:
        raise ValueError("No Hugging Face dataset was named.")
    candidate = parse_hugging_face_reference(value.strip())
    if not candidate or candidate != candidate.strip():
        raise ValueError("The Hugging Face dataset reference is empty or malformed.")
    if "://" in candidate or candidate.startswith("/") or "\\" in candidate:
        raise ValueError(
            f"'{value}' is not a Hugging Face dataset identifier. "
            "Use a hub reference such as 'owner/name' or "
            "'https://huggingface.co/datasets/owner/name'."
        )
    if ".." in candidate or "@" in candidate or any(part in ("", ".", "..") for part in candidate.split("/")):
        raise ValueError(
            f"'{value}' is not a valid Hugging Face dataset identifier."
        )
    if not _HF_DATASET_ID_PATTERN.match(candidate):
        raise ValueError(
            f"'{value}' is not a valid Hugging Face dataset identifier "
            "(expected 'name' or 'owner/name')."
        )
    return candidate


def load_huggingface_dataset(dataset_ref: str) -> Path:
    dataset_id = validate_hf_dataset_reference(dataset_ref)
    dataset = load_dataset(dataset_id)
    split_name = next(iter(dataset.keys()))
    df = dataset[split_name].to_pandas()
    if df.empty:
        raise ValueError("Loaded Hugging Face dataset is empty.")
    if "label" not in df.columns and len(df.columns) >= 2:
        label_column = df.columns[-1]
        df = df.rename(columns={label_column: "label"})
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    df.to_csv(tmp.name, index=False)
    tmp.close()
    return Path(tmp.name)


TASK_TYPES = ("classification", "regression")

# Models that only make sense for one kind of label. Naming the mismatch beats
# the cryptic error scikit-learn raises from deep inside fit().
_TASK_ONLY_MODELS = {"MLR": "regression", "Logistic_Regression": "classification"}


def infer_task_type(y: pd.Series) -> str:
    """Guess the kind of task from the label column.

    Text and booleans are classes. Numbers are classes when there are few
    distinct integer-valued ones, and a regression target otherwise. A float
    label with non-integer values is a measurement, never a class, however few
    distinct values it has. The guess can be overridden with ``task_type``.
    """
    if pd.api.types.is_bool_dtype(y) or not pd.api.types.is_numeric_dtype(y):
        return "classification"
    values = y.dropna()
    if values.empty:
        return "classification"
    if pd.api.types.is_float_dtype(values) and bool((values % 1 != 0).any()):
        return "regression"
    if values.nunique() <= 20:
        return "classification"
    return "regression"


def _check_task_fits_model(model_name: str, task_type: str, y: pd.Series) -> None:
    required = _TASK_ONLY_MODELS.get(model_name)
    if required is not None and required != task_type:
        raise ValueError(
            f"{model_name} is a {required} model, but the label column "
            f"'{y.name}' was read as {task_type} ({int(y.nunique())} distinct values). "
            f"Pick a {task_type} model, or set task_type to '{required}' if the label "
            "was misread."
        )


# Metrics for which a lower value is the better one.
_LOWER_IS_BETTER_METRICS = ("mse", "rmse", "mae")

# Metrics used to rank a candidate when the requested one is not reported by the run.
_CANDIDATE_SCORE_KEYS = ("accuracy", "r2", "rmse", "mse", "mean_reward", "silhouette")


def score_candidate(metrics: Dict[str, Any], optimize_metric: str) -> float:
    """Rank a trained candidate by a metric the run actually reports.

    The previous lookup used `or`, so a missing metric (a regression run has no
    "accuracy") collapsed every candidate to 0 and the first candidate always won.
    Missing metrics are skipped, and error metrics are negated because lower is
    better for them.
    """
    # The cross-validated score ranks the candidates when the run has one: the
    # hold-out score of the winner of several candidates is optimistic, because
    # the winner was picked on exactly those rows.
    cv_scores = ((metrics.get("cv") or {}).get("scores")) or {}
    for key in (optimize_metric, *_CANDIDATE_SCORE_KEYS):
        cv_entry = cv_scores.get(key)
        value = cv_entry.get("mean") if isinstance(cv_entry, dict) else None
        if value is None:
            value = metrics.get(key)
        if value is None:
            continue
        try:
            score = float(value)
        except (TypeError, ValueError):
            continue
        return -score if key in _LOWER_IS_BETTER_METRICS else score
    return 0.0


def safe_json(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, dict):
        return {k: safe_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [safe_json(v) for v in value]
    return value


def ensure_dict(value: Any, name: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a dictionary of hyperparameters.")
    return value


def resolve_dataset_path(dataset_name: str) -> Path:
    """The absolute path of a dataset, from its path in the registry.

    The name of a dataset is the path it has *inside the datasets root*, and
    it always comes from the registry - never from the client. The path is
    resolved and checked against the root, so a name that climbs out of it
    with ``..`` or that points at a symlink outside of it is refused.

    This is the boundary of what the application can read: before the
    registry existed, a client could send an absolute path and make the
    server read any file it could read.
    """
    from .datasets import resolve_storage_path

    return resolve_storage_path(dataset_name)


def is_image_dataset_path(dataset_name: str) -> bool:
    if not dataset_name:
        return False
    path = resolve_dataset_path(dataset_name)
    return path.exists() and path.is_dir()


def suggest_hyperparameters(
    model_name: str,
    task_type: str,
    optimize_metric: str = "accuracy",
    dataset_name: Optional[str] = None,
    hf_dataset_url: Optional[str] = None,
    use_llm: bool = False,
) -> Dict[str, Any]:
    entry = get_model_entry(model_name)
    base_params = copy.deepcopy(entry.get("params", {}))
    if use_llm:
        if genai is None or not os.getenv("GOOGLE_API_KEY"):
            raise ValueError("LLM fine tuning requires GOOGLE_API_KEY and the google-generativeai package.")
        try:
            # Configure Google Gemini API
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
            model = genai.GenerativeModel(os.getenv("GOOGLE_MODEL", "gemini-pro"))
            
            prompt = (
                f"Provide a JSON object of hyperparameters for {model_name} when training a {task_type} model. "
                f"Optimize for {optimize_metric}. "
                f"Base values: {json.dumps(base_params)}. "
                f"If the dataset is local, use the name {dataset_name}. "
                f"If the dataset is remote, use the Hugging Face reference {hf_dataset_url}. "
                f"Return ONLY valid JSON without any markdown formatting or code blocks."
            )
            response = model.generate_content(prompt)
            prediction = response.text.strip()
            
            # Remove markdown code block markers if present
            if prediction.startswith("```json"):
                prediction = prediction[7:]
            if prediction.startswith("```"):
                prediction = prediction[3:]
            if prediction.endswith("```"):
                prediction = prediction[:-3]
            prediction = prediction.strip()
            
            suggested = json.loads(prediction)
            # Only keys the catalog declares for this model are accepted: the result is
            # merged into the estimator constructor, so any other key (e.g. learning_rate
            # for LogisticRegression) would raise TypeError during training.
            base_params.update({k: v for k, v in suggested.items() if k in base_params})
            return base_params
        except Exception as exc:
            raise RuntimeError(f"LLM hyperparameter suggestion failed: {exc}")

    # Without the LLM the function returns the catalog parameters of the model as they
    # are: there is no heuristic that could add a value the catalog does not declare
    # (an undeclared key would be rejected by the estimator constructor). `auto_tune`
    # and `auto_fine_tune` run a real randomized search over the model's `search_space`
    # in `train_model()`; this function only provides the catalogue base.
    return base_params


def build_model(model_name: str, task_type: str, params: Dict[str, Any], class_weight: str = "none"):
    # Trainer-owned keys (e.g. test_size) are removed before the constructor call; every
    # other key is forwarded as-is so invalid names still raise TypeError.
    estimator_params = {k: v for k, v in params.items() if k not in _TRAINER_OWNED_PARAMS}
    if class_weight == "balanced" and task_type == "classification":
        # Only the estimators that accept the option receive it (plan C6):
        # a regressor has no class weights, and the boosters handle the
        # rare classes differently.
        if model_name in ("Random_Forest", "Logistic_Regression", "SVM"):
            estimator_params = {**estimator_params, "class_weight": "balanced"}
    if model_name == "Random_Forest":
        if task_type == "classification":
            return RandomForestClassifier(**estimator_params)
        return RandomForestRegressor(**estimator_params)
    if model_name == "Logistic_Regression":
        return LogisticRegression(**estimator_params)
    if model_name == "MLR":
        return LinearRegression(**estimator_params)
    if model_name == "KNN":
        if task_type == "classification":
            return KNeighborsClassifier(**estimator_params)
        return KNeighborsRegressor(**estimator_params)
    if model_name == "SVM":
        if task_type == "classification":
            # "probability" and "random_state" are set inside the dict: passing them
            # twice raised "SVC() got multiple values for keyword argument ...". The
            # seed is needed because probability=True enables the internal Platt
            # calibration, which shuffles the data and is otherwise not reproducible.
            svc_params = dict(estimator_params)
            svc_params["probability"] = True
            seed = svc_params.get("random_state")
            svc_params["random_state"] = 42 if seed is None else seed
            return SVC(**svc_params)
        # The regression branch is SVR: it accepts neither "probability" nor
        # "random_state" (scikit-learn >= 1.9), so both are dropped here.
        return SVR(**{k: v for k, v in estimator_params.items() if k not in _BRANCH_SPECIFIC_PARAMS})
    if model_name == "XGboost_timeseries":
        if xgb is None:
            raise RuntimeError("xgboost is not installed")
        if task_type == "classification":
            # The forced value must not collide with a client-supplied one, otherwise
            # XGBClassifier() raises "got multiple values for keyword argument".
            xgb_params = {**estimator_params, "eval_metric": estimator_params.get("eval_metric", "logloss")}
            return xgb.XGBClassifier(**xgb_params)
        return xgb.XGBRegressor(**estimator_params)
    if model_name == "lightGBM_timeseries":
        if lgb is None:
            raise RuntimeError("lightgbm is not installed")
        # LightGBM logs every split to the console by default; with a
        # cross-validation that is hundreds of lines per run.
        lgb_params = {**estimator_params, "verbose": estimator_params.get("verbose", -1)}
        if task_type == "classification":
            return lgb.LGBMClassifier(**lgb_params)
        return lgb.LGBMRegressor(**lgb_params)
    if model_name == "CATboost_timeseries":
        if cb is None:
            raise RuntimeError("catboost is not installed")
        # Same as above: "verbose" is forced, so it is merged into the dict instead of
        # being passed as a separate keyword.
        cb_params = {
            **estimator_params,
            "verbose": estimator_params.get("verbose", 0),
            # CatBoost writes a catboost_info/ directory into the working directory by default.
            "allow_writing_files": estimator_params.get("allow_writing_files", False),
        }
        if task_type == "classification":
            return cb.CatBoostClassifier(**cb_params)
        return cb.CatBoostRegressor(**cb_params)
    raise ValueError(f"Unsupported model: {model_name}")


_AUTOENCODER_PARAMS = frozenset(
    {
        "latent_dim",
        "hidden_units",
        "activation",
        "epochs",
        "batch_size",
        "learning_rate",
        "weight_decay",
        "anomaly_quantile",
        "random_state",
    }
)


def _train_autoencoder(
    dataset: pd.DataFrame,
    label_column: str,
    params: Dict[str, Any],
    test_size: float,
    random_state: int,
) -> Tuple[Dict[str, Any], AutoencoderBundle, "FeaturePlan"]:
    """Train a real autoencoder: encoder, bottleneck, decoder.

    The network is ``features -> hidden -> latent -> hidden -> features`` (just
    ``features -> latent -> features`` when ``hidden_units`` is 0), trained to
    reproduce its own input. The input is preprocessed like every tabular
    model's (imputed, one-hot encoded, standardised), and the reconstruction
    error is reported on rows the network did not train on, next to the error
    of the trivial reconstruction (the mean of every column): an error that
    does not beat that baseline means the bottleneck learned nothing.

    A label column, if the file has one, is ignored: the model is unsupervised.
    """
    unknown = sorted(set(params) - _AUTOENCODER_PARAMS)
    if unknown:
        raise TypeError(f"Autoencoder got unexpected parameter(s): {unknown}")
    latent_dim = int(params["latent_dim"])
    hidden_units = int(params.get("hidden_units", 0))
    activation = str(params.get("activation", "relu"))
    quantile = float(params.get("anomaly_quantile", 0.95))
    if latent_dim < 1:
        raise ValueError("latent_dim must be at least 1.")
    if hidden_units < 0:
        raise ValueError("hidden_units cannot be negative.")
    if activation not in {"relu", "tanh", "logistic", "identity"}:
        raise ValueError(
            f"activation must be one of ['relu', 'tanh', 'logistic', 'identity'], got '{activation}'."
        )
    if not 0.5 <= quantile < 1.0:
        raise ValueError("anomaly_quantile must be in [0.5, 1).")

    X_raw = dataset.drop(columns=[label_column]) if label_column in dataset.columns else dataset
    plan = analyze_features(X_raw)
    X = coerce_features(X_raw, plan)
    X_train, X_test = train_test_split(X, test_size=test_size, random_state=random_state)

    preprocessor = build_preprocessor(plan, scale=True)
    Z_train = preprocessor.fit_transform(X_train)
    Z_test = preprocessor.transform(X_test)

    layers = (hidden_units, latent_dim, hidden_units) if hidden_units else (latent_dim,)
    network = MLPRegressor(
        hidden_layer_sizes=layers,
        activation=activation,
        alpha=float(params.get("weight_decay", 0.0001)),
        batch_size=min(int(params.get("batch_size", 32)), len(Z_train)),
        learning_rate_init=float(params.get("learning_rate", 0.001)),
        max_iter=int(params.get("epochs", 200)),
        random_state=int(params.get("random_state", random_state)),
    )
    with warnings.catch_warnings():
        # Reaching max_iter without converging is reported in the metrics
        # ("converged"); the warning would only be noise in the server log.
        warnings.simplefilter("ignore", category=ConvergenceWarning)
        network.fit(Z_train, Z_train)

    bundle = AutoencoderBundle(
        preprocessor=preprocessor,
        network=network,
        bottleneck_layers=2 if hidden_units else 1,
        activation=activation,
        plan=plan,
        threshold=0.0,
        quantile=quantile,
        feature_schema=describe_features(X_train, plan),
    )
    train_errors = bundle.reconstruction_error(Z_train)
    bundle.threshold = float(np.quantile(train_errors, quantile))
    test_errors = bundle.reconstruction_error(Z_test)

    mse = float(np.mean(test_errors))
    # The trivial reconstruction: every column is replaced by its training mean,
    # which is 0 once the columns are standardised.
    baseline = float(np.mean(Z_test ** 2))
    metrics = {
        "task_type": "autoencoder",
        "reconstruction_mse": safe_json(mse),
        "baseline_mse": safe_json(baseline),
        "reconstruction_r2": safe_json(1.0 - mse / baseline) if baseline > 0 else None,
        "train_reconstruction_mse": safe_json(float(np.mean(train_errors))),
        "latent_dim": latent_dim,
        "encoded_feature_count": int(Z_train.shape[1]),
        "epochs_run": int(network.n_iter_),
        "converged": bool(network.n_iter_ < network.max_iter),
        "anomaly_threshold": safe_json(bundle.threshold),
        "anomaly_quantile": quantile,
        "test_anomaly_rate": safe_json(float(np.mean(test_errors > bundle.threshold))),
        "train_size": len(X_train),
        "test_size": len(X_test),
        "feature_count": len(plan.columns),
        "artifact_kind": AutoencoderBundle.kind,
        "preprocessing": preprocessing_report(X_raw, plan, True, 0),
    }
    return metrics, bundle, plan


def write_artifact(model_name: str, bundle: Any) -> Dict[str, Any]:
    """Write the artifact of a run through the bundle contract (plan C1).

    The artifact is a directory with a ``bundle.json`` manifest (the kind,
    the format version, the schema, the sha256 of every file), and the
    answer is the record the run row stores: the path, the checksum that is
    verified before every load, and the size. ``MODEL_DIR`` is read at call
    time, so the test suite can redirect it.
    """
    return write_bundle(model_name, bundle, model_dir=MODEL_DIR)


def _prepare_dataset(
    dataset_name: Optional[str],
    hf_dataset_url: Optional[str],
    label_column: str,
    sep: Optional[str],
    usecols: Optional[List[str]],
) -> Tuple[pd.DataFrame, str, str]:
    if dataset_name:
        local_path = resolve_dataset_path(dataset_name)
        if not local_path.exists():
            raise FileNotFoundError(f"Local dataset '{dataset_name}' not found at '{local_path}'.")
        if local_path.is_dir():
            raise ValueError(
                "The dataset is a folder. For image datasets use a vision-capable model like ResNet50 "
                "and a dataset whose source is 'folder', or pick a CSV dataset for the tabular models."
            )
        try:
            df = pd.read_csv(local_path, sep=sep, usecols=usecols)
        except pd.errors.EmptyDataError:
            raise ValueError(f"Local dataset '{dataset_name}' is empty.")
        except (pd.errors.ParserError, UnicodeDecodeError) as exc:
            raise ValueError(f"Could not parse local dataset '{dataset_name}': {exc}")
        dataset_source = "local"
        dataset_tag = dataset_name
    elif hf_dataset_url:
        file_path = str(load_huggingface_dataset(hf_dataset_url))
        try:
            df = pd.read_csv(file_path, sep=sep, usecols=usecols)
        except pd.errors.EmptyDataError:
            raise ValueError(f"Hugging Face dataset '{hf_dataset_url}' is empty or invalid.")
        except (pd.errors.ParserError, UnicodeDecodeError) as exc:
            raise ValueError(f"Could not parse Hugging Face dataset '{hf_dataset_url}': {exc}")
        finally:
            try:
                os.remove(file_path)
            except OSError:
                pass
        dataset_source = "huggingface"
        dataset_tag = hf_dataset_url
    else:
        raise ValueError("Either dataset_name or hf_dataset_url must be provided.")

    if df.empty:
        raise ValueError("The dataset contains no rows.")
    if label_column and label_column not in df.columns:
        raise ValueError(f"label column '{label_column}' not found in dataset.")
    return df, dataset_source, dataset_tag


def _searchable_space(model_def: Dict[str, Any], client_values: Dict[str, Any]) -> Dict[str, Any]:
    """The curated search space of a catalog entry.

    The keys the client pinned are removed: they are not sampled, because the
    client wins and must keep its value. Trainer-owned keys (test_size) are
    removed too.
    """
    space = copy.deepcopy(model_def.get("search_space", {})) or {}
    for key in list(space):
        if key in client_values or key in _TRAINER_OWNED_PARAMS:
            del space[key]
    return space


# Float parameters that are fractions (0 < value <= 1): they cannot be scaled up freely.
_FRACTION_PARAMS = frozenset(
    {
        "subsample",
        "colsample_bytree",
        "colsample_bylevel",
        "colsample_bynode",
        "bagging_fraction",
        "feature_fraction",
        "rsm",
        "l1_ratio",
        "max_samples",
        "max_features",
    }
)


def _neighborhood_space(base_params: Dict[str, Any]) -> Dict[str, Any]:
    """A narrow search space centred on the base parameters.

    Used by auto_fine_tune: a local search around the current configuration
    instead of a full re-search of the catalogue space.
    """
    space: Dict[str, Any] = {}
    for key, value in base_params.items():
        if key in _TRAINER_OWNED_PARAMS or key == "random_state":
            continue
        if isinstance(value, bool):
            space[key] = [value]
        elif isinstance(value, int):
            space[key] = [max(1, int(value * 0.5)), value, max(1, int(value * 2))]
        elif isinstance(value, float) and key in _FRACTION_PARAMS:
            # A fraction lives in (0, 1]: doubling 0.8 gives 1.6, which the
            # estimator rejects (and a rejected candidate silently disappears
            # from the search).
            space[key] = sorted({round(value * 0.5, 6), value, min(1.0, round(value * 1.25, 6))})
        elif isinstance(value, float):
            space[key] = [round(value * 0.5, 6), value, round(value * 2, 6)]
        elif isinstance(value, list):
            # Already an enumerated choice: keep it as the only option.
            space[key] = value
        else:
            # Strings, None and anything else: keep the current value fixed.
            space[key] = [value]
    return space


def _top_candidates(cv_results: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    """The best candidates of a search, ranked, as plain JSON-serialisable dicts."""
    ranks = cv_results.get("rank_test_score", [])
    order = sorted(range(len(ranks)), key=lambda i: ranks[i])[:limit]
    out: List[Dict[str, Any]] = []
    for i in order:
        params = cv_results["params"][i]
        out.append(
            {
                "params": safe_json({k.removeprefix("model__"): v for k, v in params.items()}),
                "mean_test_score": safe_json(cv_results["mean_test_score"][i]),
                "rank": int(cv_results["rank_test_score"][i]),
            }
        )
    return out


def _run_hyperparameter_search(
    model_name: str,
    task_type: str,
    model_def: Dict[str, Any],
    X_train: Any,
    y_train: Any,
    space: Dict[str, Any],
    optimize_metric: str,
    random_state: int,
    preprocessor: Optional[Any] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], int]:
    """Run a randomized hyperparameter search on the training split.

    Returns (best_params, search_results, cv_used). When the search cannot run
    (no searchable parameters, a missing optional dependency, or a fold that is
    too small even for cv=2) it returns ({}, [], cv_used) so the caller falls
    back to the plain effective parameters.
    """
    if not space:
        return {}, [], 0

    scoring = "accuracy" if task_type == "classification" else "r2"
    base_params = {
        k: v
        for k, v in model_def.get("params", {}).items()
        if k not in _TRAINER_OWNED_PARAMS
    }
    total_combinations = 1
    for values in space.values():
        total_combinations *= len(values)
    n_iter = max(1, min(12, total_combinations))
    cv = 3
    search_results: List[Dict[str, Any]] = []
    best_params: Dict[str, Any] = {}

    def _fit(cv_value: int) -> None:
        nonlocal cv, search_results, best_params
        estimator = build_model(model_name, task_type, base_params)
        distributions = space
        if preprocessor is not None:
            # The preprocessor is refitted inside every fold, so the search
            # never sees the statistics of the rows it is scored on.
            estimator = Pipeline([("prep", clone(preprocessor)), ("model", estimator)])
            distributions = {f"model__{key}": value for key, value in space.items()}
        search = RandomizedSearchCV(
            estimator=estimator,
            param_distributions=distributions,
            n_iter=n_iter,
            cv=cv_value,
            scoring=scoring,
            refit=True,
            random_state=random_state,
        )
        search.fit(X_train, y_train)
        cv = cv_value
        search_results = _top_candidates(search.cv_results_)
        best_params = safe_json(
            {key.removeprefix("model__"): value for key, value in search.best_params_.items()}
        )

    try:
        _fit(3)
    except Exception as exc:
        message = str(exc).lower()
        if cv == 3 and (
            "fold" in message or "split" in message or "sample" in message
        ):
            # The training fold is too small for cv=3: retry with cv=2 and say so.
            try:
                _fit(2)
                for c in search_results:
                    c["cv_used"] = 2
            except Exception:
                return {}, [], 2
        else:
            return {}, [], 3

    for c in search_results:
        c["cv_used"] = cv
    return best_params, search_results, cv


def train_model(
    model_name: str,
    dataset_name: Optional[str],
    hf_dataset_url: Optional[str],
    label_column: str,
    test_size: float,
    random_state: int,
    hyperparameters: Dict[str, Any],
    sep: Optional[str] = ",",
    usecols: Optional[List[str]] = None,
    mode: str = "manual",
    optimize_metric: str = "accuracy",
    env_id: Optional[str] = None,
    model_candidates: Optional[List[str]] = None,
    preset: str = "balanced",
    task_type: Optional[str] = None,
    cv_folds: int = 5,
    preprocessing: Optional[Dict[str, Any]] = None,
    split: Optional[Dict[str, Any]] = None,
    time_column: Optional[str] = None,
) -> Tuple[Dict[str, Any], str, str, Dict[str, Any]]:
    # ``task_type`` overrides the guess made from the label column, and
    # ``cv_folds`` (< 2 disables it) sets the cross-validation of the tabular
    # models. ``preprocessing`` and ``split`` are the user-steerable options of
    # plans C6 and C7, and ``time_column`` names the time column of a
    # chronological split or a forecast. All are optional and trailing, so
    # existing callers are unaffected.
    # ``task_type`` overrides the guess made from the label column, and
    # ``cv_folds`` (< 2 disables it) sets the cross-validation of the tabular
    # models. Both are optional and trailing, so existing callers are unaffected.
    task_type_override = task_type
    if task_type_override is not None and task_type_override not in TASK_TYPES:
        raise ValueError(f"task_type must be one of {list(TASK_TYPES)}, got '{task_type_override}'.")
    model_name = normalize_model_name(model_name)
    if mode not in TRAINING_MODES:
        raise ValueError(f"Unsupported training mode '{mode}'.")
    if model_name not in MODEL_CATALOG:
        raise ValueError(f"Model '{model_name}' is not supported for training.")
    
    hyperparameters = ensure_dict(hyperparameters, "hyperparameters")
    
    # Trainer-owned keys (e.g. test_size) configure the training loop, not the
    # estimator: they are dropped from the client-supplied hyperparameters here, so no
    # estimator constructor can ever receive them. The split is governed by the
    # top-level test_size argument, a client-supplied hyperparameters["test_size"] is
    # ignored. Every other key is kept, so a typo still raises TypeError later on.
    hyperparameters = {k: v for k, v in hyperparameters.items() if k not in _TRAINER_OWNED_PARAMS}
    
    # The raw client values (the trainer-owned keys are already stripped). They are
    # kept unadjusted on purpose: the preset is applied by _effective_params() below,
    # exactly once, to the merged base - never to the raw request. Adjusting the
    # request here would make the preset a no-op for the modes whose requests carry
    # an empty "hyperparameters" dict (the catalog defaults are merged in later and
    # would never be scaled).
    user_hyperparameters = hyperparameters
    
    model_def = get_model_entry(model_name)
    
    # A placeholder entry advertises a model it cannot train: fail fast instead of
    # silently training something else (an MLP in disguise for Autoencoder/GNN/LSTM/...,
    # a ResNet for ViT, a stub for Q-Learning). No artifact is written for such a run.
    if not model_def.get("implemented", True):
        raise ValueError(
            f"Model '{model_name}' is not implemented: it does not train what the "
            f"catalog advertises. Pick an implemented model or wait for a real trainer."
        )
    
    def _effective_params(suggested: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Merge the catalog defaults, the mode suggestions and the client's values.

        The preset is applied exactly once, to the merged base, so it scales the
        catalog/suggested values even when the client sends an empty
        ``hyperparameters`` dict. The client's own values are scaled as well and
        still win over the base.
        """
        base = {**model_def["params"], **(suggested or {})}
        client = apply_preset(user_hyperparameters, preset)
        if preset and preset in TRAINING_PRESETS:
            base = apply_preset(base, preset)
        return {**base, **client}
    
    # The category of the catalog entry selects the training path - see the routing
    # table in backend/app/README.md.
    
    # REINFORCEMENT LEARNING MODELS (plan F2 and C5): Q-Learning is the
    # textbook table; PPO and DQN are evaluated on fresh episodes with fixed
    # seeds, next to a uniformly random policy.
    if model_def["category"] == "reinforcement-learning":
        if env_id is None:
            raise ValueError("env_id is required for reinforcement learning models.")
        if model_name == "Q-Learning":
            metrics, bundle = rl_module.train_q_learning(env_id, _effective_params())
        else:
            metrics, bundle = rl_module.train_deep_rl(model_name, env_id, _effective_params())
        artifact = write_artifact(model_name, bundle)
        return metrics, "rl", env_id, artifact
    
    # VISION MODELS (plan C3 and F5): a stratified split, augmentation only
    # on the training transform, validation metrics with a baseline, early
    # stopping, and an artifact that carries the exact transform.
    if model_def["category"] == "vision":
        if not dataset_name or not is_image_dataset_path(dataset_name):
            raise ValueError(
                "Vision models require a dataset that is a folder with one subdirectory per class. "
                "Pick one of the datasets of the list whose source is 'folder'."
            )
        vision_suggested: Dict[str, Any] = {}
        if mode in {"auto_tune", "auto_fine_tune", "llm_fine_tune"}:
            vision_suggested = suggest_hyperparameters(
                model_name, "classification", optimize_metric, dataset_name, hf_dataset_url,
                use_llm=(mode == "llm_fine_tune"),
            )
            if mode == "auto_fine_tune" and "learning_rate" in vision_suggested:
                vision_suggested["learning_rate"] = vision_suggested["learning_rate"] * 0.1
        architecture = "vit" if model_name == "ViT" else ("resnet50" if model_name == "ResNet50" else "resnet18")
        metrics, bundle = vision_module.train_image_model(
            model_name,
            resolve_dataset_path(dataset_name),
            _effective_params(vision_suggested),
            architecture,
            list(model_def.get("allowed_checkpoints") or []),
        )
        artifact = write_artifact(model_name, bundle)
        return metrics, "local", dataset_name, artifact

    # THE GRAPH MODELS (plan F4): the dataset is a zip of nodes.csv and
    # edges.csv; the GNN is full-batch with a feature-only baseline.
    if model_def["category"] == "graph":
        if not dataset_name:
            raise ValueError("The graph models need a dataset (a zip of nodes.csv and edges.csv).")
        # The mode's suggestions are resolved here (this branch runs before
        # the shared dataset preparation, which is where mode_suggested is
        # normally built).
        graph_suggested: Dict[str, Any] = {}
        if mode in {"auto_tune", "auto_fine_tune", "llm_fine_tune"}:
            graph_suggested = suggest_hyperparameters(
                model_name, "classification", optimize_metric, dataset_name, hf_dataset_url,
                use_llm=(mode == "llm_fine_tune"),
            )
        metrics, bundle = graph_module.train_gnn(
            model_name, resolve_dataset_path(dataset_name), _effective_params(graph_suggested)
        )
        artifact = write_artifact(model_name, bundle)
        return metrics, "local", dataset_name, artifact

    # Load and validate dataset for non-vision models
    dataset, dataset_source, dataset_tag = _prepare_dataset(dataset_name, hf_dataset_url, label_column, sep, usecols)
    
    # Infer task type for mode-based hyperparameter adjustment
    task_type = "classification"
    if model_def["category"] == "clustering":
        task_type = "clustering"
    elif label_column in dataset.columns:
        task_type = task_type_override or infer_task_type(dataset[label_column])
    
    # AUTO_SEARCH: Try multiple model candidates
    if mode == "auto_search" and model_candidates:
        best_score = None
        best_result = None
        best_candidate = None
        for candidate in model_candidates:
            try:
                # Only the parameters the candidate itself declares are forwarded.
                # In the single-model path an unknown key still raises TypeError
                # (that contract is deliberate: a silently ignored parameter is
                # worse than a loud failure), but in a multi-candidate search a
                # parameter that a candidate does not accept would make that
                # candidate fail and silently disappear from the comparison.
                candidate_params = {
                    key: value
                    for key, value in user_hyperparameters.items()
                    if key in get_model_entry(candidate).get("params", {})
                }
                candidate_metrics, ds, ds_tag, artifact_path = train_model(
                    candidate,
                    dataset_name,
                    hf_dataset_url,
                    label_column,
                    test_size,
                    random_state,
                    candidate_params,
                    sep,
                    usecols,
                    "manual",
                    optimize_metric,
                    env_id,
                    preset=preset,
                    task_type=task_type_override,
                    cv_folds=cv_folds,
                )
                score = score_candidate(candidate_metrics, optimize_metric)
                # "best_score is None" (not "or score") so that a legitimate score of 0
                # is kept as the incumbent instead of being discarded.
                if best_score is None or score > best_score:
                    best_score = score
                    best_result = (candidate_metrics, ds, ds_tag, artifact_path)
                    best_candidate = candidate
            except Exception as exc:
                continue
        if best_result is None:
            raise ValueError("Auto-search failed to train any candidate models.")
        # Annotate result with best candidate info
        best_result[0]["best_candidate"] = best_candidate
        return best_result
    
    # The mode's own suggestions. They are merged into the base by
    # _effective_params() at the leaf (the single merge point of the run); they
    # never overwrite the client's values.
    mode_suggested: Dict[str, Any] = {}
    
    # Mode: AUTO_TUNE - Grid search over key hyperparameters
    if mode == "auto_tune":
        mode_suggested = suggest_hyperparameters(
            model_name,
            task_type,
            optimize_metric,
            dataset_name,
            hf_dataset_url,
            use_llm=False,
        )
    
    # Mode: AUTO_FINE_TUNE - Adaptive parameter adjustment
    elif mode == "auto_fine_tune":
        mode_suggested = suggest_hyperparameters(
            model_name,
            task_type,
            optimize_metric,
            dataset_name,
            hf_dataset_url,
            use_llm=False,
        )
        # Apply fine-tuning adjustments: lower learning rate for stability
        if "learning_rate" in mode_suggested:
            mode_suggested["learning_rate"] = mode_suggested["learning_rate"] * 0.1
        if "epochs" in mode_suggested:
            mode_suggested["epochs"] = max(1, int(mode_suggested["epochs"] * 0.5))
    
    # Mode: LLM_FINE_TUNE - AI-guided parameter selection
    elif mode == "llm_fine_tune":
        mode_suggested = suggest_hyperparameters(
            model_name,
            task_type,
            optimize_metric,
            dataset_name,
            hf_dataset_url,
            use_llm=True,
        )
    
    # CLUSTERING MODELS (plan C2): the preprocessing of the tabular path,
    # held-out scoring where the model has an out-of-sample step, honest
    # metrics with a baseline, and prediction only where the model can.
    if model_def["category"] == "clustering":
        metrics, bundle = clustering_module.train_clustering_model(
            model_name,
            dataset,
            label_column,
            _effective_params(mode_suggested),
            test_size=test_size,
            random_state=random_state,
        )
        artifact = write_artifact(model_name, bundle)
        return metrics, dataset_source, dataset_tag, artifact
    
    # NLP MODELS (plan C4 and F6): the classifiers get a stratified held-out
    # split; the generation family (GPT, seq2seq, BERT2BERT, LLaMA) trains on
    # the text or text-pairs columns and reports held-out perplexity or ROUGE
    # against real baselines. Every checkpoint comes from the allow-list.
    if model_def["category"] == "nlp":
        task = model_def.get("task", "classification")
        effective = _effective_params(mode_suggested)
        if task == "generation":
            if model_name == "LLaMA":
                metrics, bundle = text_module.train_llama_lora(
                    model_name, dataset, label_column, effective, model_def
                )
            else:
                metrics, bundle = text_module.train_language_model(
                    model_name, dataset, label_column, effective, model_def
                )
        elif task == "seq2seq":
            metrics, bundle = text_module.train_seq2seq(
                model_name, dataset, label_column, effective, model_def
            )
        else:
            metrics, bundle = text_module.train_text_classifier(
                model_name, model_def, dataset, label_column, effective
            )
        artifact = write_artifact(model_name, bundle)
        return metrics, dataset_source, dataset_tag, artifact
    
    # AUTOENCODER: a real encoder-bottleneck-decoder (unsupervised)
    if model_def["category"] == "autoencoder":
        metrics, bundle, _plan = _train_autoencoder(
            dataset,
            label_column,
            _effective_params(mode_suggested),
            test_size,
            random_state,
        )
        artifact = write_artifact(model_name, bundle)
        return metrics, dataset_source, dataset_tag, artifact

    # THE FORECASTING FAMILY (plan F3): RNN, LSTM, TCN and SSM share one
    # contract - a chronological split, direct multi-step prediction and the
    # naive baselines - so the comparison view is meaningful.
    if model_def["category"] == "timeseries":
        effective = _effective_params(mode_suggested)
        effective.setdefault("test_size", test_size)
        effective.setdefault("random_state", random_state)
        if time_column:
            effective["time_column"] = time_column
        metrics, bundle = forecasting_module.train_forecaster(
            model_name, dataset, label_column, effective,
            time_column=effective.get("time_column"),
        )
        artifact = write_artifact(model_name, bundle)
        return metrics, dataset_source, dataset_tag, artifact


    
    # THE BOOSTERS IN FORECASTING MODE (plan F3): the same shared contract as
    # the neural forecasters - lag features, a chronological split and the
    # naive baselines - behind a hyperparameter, because these three entries
    # are ordinary tabular regressors otherwise.
    if bool(hyperparameters.get("forecasting")) and model_def["category"] == "time-series":
        effective = _effective_params(mode_suggested)
        effective.setdefault("test_size", test_size)
        effective.setdefault("random_state", random_state)
        if time_column:
            effective["time_column"] = time_column
        metrics, bundle = forecasting_module.train_forecaster(
            model_name, dataset, label_column, effective,
            time_column=effective.get("time_column"),
        )
        artifact = write_artifact(model_name, bundle)
        return metrics, dataset_source, dataset_tag, artifact

    # STANDARD TABULAR MODELS (Random Forest, SVM, LR, etc.)
    if label_column not in dataset.columns:
        raise ValueError(f"label column '{label_column}' not found in dataset.")

    # A row without a label cannot be trained on nor scored.
    rows_without_label = int(dataset[label_column].isna().sum())
    if rows_without_label:
        dataset = dataset[dataset[label_column].notna()]
        if dataset.empty:
            raise ValueError(f"The label column '{label_column}' has no value in any row.")

    y = dataset[label_column]
    X_raw = dataset.drop(columns=[label_column])
    task_type = task_type_override or infer_task_type(y)
    _check_task_fits_model(model_name, task_type, y)

    # Preprocessing: what is done to every column is decided here (from the
    # columns alone), and fitted inside the pipeline below. The options of
    # plan C6 steer it; their defaults equal the behaviour the requests
    # without options always had.
    preprocessing_options = parse_preprocessing_options(preprocessing)
    split_options = parse_split_options(split)
    plan = analyze_features(X_raw, preprocessing_options)
    X = coerce_features(X_raw, plan)
    scale = (
        preprocessing_options.scale == "on"
        or (preprocessing_options.scale == "auto" and model_name in SCALE_SENSITIVE_MODELS)
    )

    label_encoder: Optional[LabelEncoder] = None
    if task_type == "classification":
        if y.nunique() < 2:
            raise ValueError(
                f"The label column '{label_column}' has a single class: there is nothing to classify."
            )
        # Every estimator trains on 0..k-1 (XGBoost requires it); the bundle
        # decodes the predictions back to the original labels.
        label_encoder = LabelEncoder().fit(y)
        y_model = pd.Series(label_encoder.transform(y), index=y.index, name=label_column)
    else:
        try:
            y_model = pd.to_numeric(y, errors="raise").astype(float)
        except (TypeError, ValueError):
            raise ValueError(
                f"The label column '{label_column}' must be numeric for a regression "
                f"(task_type is '{task_type}')."
            )

    X_train, X_test, y_train, y_test, stratified, split_warnings = split_data(
        X, y_model, task_type, test_size, random_state,
        options=split_options, split_frame=dataset,
    )

    search_results: List[Dict[str, Any]] = []
    cv_used = 0
    if mode in {"auto_tune", "auto_fine_tune"}:
        if mode == "auto_tune":
            # A randomized search over the curated, per-model space. Client-pinned
            # keys are sampled out: they keep their value and win over the search.
            space = _searchable_space(model_def, user_hyperparameters)
        else:
            # auto_fine_tune: the same search engine, restricted to a narrow
            # neighbourhood of the current configuration.
            base = {k: v for k, v in model_def.get("params", {}).items() if k not in _TRAINER_OWNED_PARAMS}
            space = _neighborhood_space(base)
        best_params, search_results, cv_used = _run_hyperparameter_search(
            model_name,
            task_type,
            model_def,
            X_train,
            y_train,
            space,
            optimize_metric,
            random_state,
            preprocessor=build_preprocessor(plan, scale, preprocessing_options),
        )
        # The search found the best values over the searchable space; the client's
        # values still win when they are merged below by _effective_params().
        mode_suggested = best_params

    effective = _effective_params(mode_suggested)
    pipeline = Pipeline(
        [
            ("prep", build_preprocessor(plan, scale, preprocessing_options)),
            ("model", build_model(model_name, task_type, effective, class_weight=preprocessing_options.class_weight)),
        ]
    )
    pipeline.fit(X_train, y_train)

    predictions = pipeline.predict(X_test)
    probabilities = None
    if task_type == "classification" and hasattr(pipeline, "predict_proba"):
        probabilities = pipeline.predict_proba(X_test)
    held_out = evaluate_holdout(
        task_type,
        y_train.to_numpy(),
        y_test.to_numpy(),
        np.asarray(predictions),
        probabilities,
        list(label_encoder.classes_) if label_encoder is not None else None,
    )

    try:
        encoded_feature_count = int(pipeline.named_steps["prep"].transform(X_train.head(1)).shape[1])
    except Exception:
        encoded_feature_count = None

    report = preprocessing_report(
        X_raw,
        plan,
        scale,
        rows_without_label,
        stratified=stratified if task_type == "classification" else None,
        task_type_source="request" if task_type_override else "inferred",
    )
    # The options that were applied (plan C6) and the warnings of the split
    # (plan C7) travel with the report, so the run page can show them.
    report["options"] = {
        "scale": preprocessing_options.scale,
        "numeric_impute": preprocessing_options.numeric_impute,
        "categorical": preprocessing_options.categorical,
        "max_categories": preprocessing_options.max_categories,
        "drop_columns": preprocessing_options.drop_columns,
        "class_weight": preprocessing_options.class_weight,
        "split_method": split_options.method,
    }
    if split_warnings:
        report["warnings"] = split_warnings

    metrics: Dict[str, Any] = {
        "task_type": task_type,
        # The keys every consumer already reads stay present (and None when they
        # do not apply to the task); the evaluation fills in the real ones.
        "accuracy": None,
        "mse": None,
        "r2": None,
        **held_out,
        "train_size": len(X_train),
        "test_size": len(X_test),
        "feature_count": len(plan.columns),
        "encoded_feature_count": encoded_feature_count,
        # What the artifact is: a bundle that knows its columns and can predict
        # (the UI offers the prediction form for these runs only).
        "artifact_kind": TabularModelBundle.kind,
        # The parameters that were really used: the catalog defaults, the mode's
        # suggestions and the client's values, with the preset applied once.
        "model_parameters": safe_json(effective),
        "preprocessing": report,
    }

    cv = cross_validate_pipeline(pipeline, X_train, y_train.to_numpy(), task_type, cv_folds, random_state)
    metrics["cv"] = cv
    primary = "accuracy" if task_type == "classification" else "r2"
    if cv.get("scores", {}).get(primary):
        metrics["cv_metric"] = primary
        metrics["cv_score_mean"] = cv["scores"][primary]["mean"]
        metrics["cv_score_std"] = cv["scores"][primary]["std"]

    if search_results:
        metrics["search_results"] = search_results
        metrics["search_cv"] = cv_used

    # --- the chart data (plan E1), computed here from the held-out rows the
    # trainer already holds; the runner moves "_charts" into the charts column.
    try:
        confusion = None
        raw_confusion = (held_out.get("confusion_matrix") or {}).get("matrix")
        if raw_confusion:
            confusion = np.asarray(raw_confusion)
        if task_type == "classification":
            charts = build_classification_charts(
                y_test.to_numpy(),
                np.asarray(predictions),
                probabilities,
                list(label_encoder.classes_) if label_encoder is not None else None,
                confusion=confusion,
            )
        else:
            charts = build_regression_charts(y_test.to_numpy(), np.asarray(predictions))
        fold_chart = cv_fold_chart(cv)
        if fold_chart:
            charts["cv_folds"] = fold_chart
        # The top-20 permutation importances on the held-out rows (plan D5):
        # a prediction with no reason is hard to trust, and this costs one
        # prediction per feature.
        importances = permutation_importances(
            lambda frame: pipeline.predict(frame),
            X_test,
            y_test.to_numpy(),
            (lambda truth, preds: accuracy_score(truth, preds))
            if task_type == "classification"
            else (lambda truth, preds: r2_score(truth, preds)),
            plan,
            seed=random_state,
        )
        if importances:
            charts["importances"] = importances
        metrics["_charts"] = cap_charts(charts)
    except Exception:
        # The charts are a view on the run, never a part of its result: a
        # failure to draw must not fail the training.
        pass

    bundle = TabularModelBundle(
        pipeline=pipeline,
        plan=plan,
        model_name=model_name,
        task_type=task_type,
        label_column=label_column,
        feature_schema=describe_features(X_train, plan),
        label_encoder=label_encoder,
    )
    artifact = write_artifact(model_name, bundle)
    return metrics, dataset_source, dataset_tag, artifact


def build_train_payload(run_id: int, model_name: str, dataset_source: str, dataset_tag: str, hyperparameters: Dict[str, Any], metrics: Dict[str, Any], artifact_path: str) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "model_name": model_name,
        "dataset_source": dataset_source,
        "dataset_tag": dataset_tag,
        "hyperparameters": safe_json(hyperparameters),
        "metrics": safe_json(metrics),
        "artifact_path": artifact_path,
        "completed_at": datetime.utcnow().isoformat() + "Z",
    }


