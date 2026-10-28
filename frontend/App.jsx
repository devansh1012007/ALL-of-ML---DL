import React, { useState, useEffect, createContext, useContext, useCallback, useRef } from 'react';
import { AdminScreen } from './AdminScreen';

// --- CONFIGURATION ---
const API_BASE = 'http://localhost:8010';
// How often a run that is still going is read again. The training runs in the
// background, so the metrics of a run appear when a poll sees them.
const RUN_POLL_INTERVAL_MS = 2000;

// --- UTILITIES ---
// JWT segments are base64url encoded ("-" / "_" instead of "+" / "/"), so they must be
// translated and padded before atob() can decode them.
const parseJwt = (token) => {
  try {
    if (!token || typeof token !== 'string') return null;
    const segment = token.split('.')[1];
    if (!segment) return null;
    const base64 = segment.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
    const binary = atob(padded);
    const percentEncoded = binary.split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join('');
    let json;
    try {
      json = decodeURIComponent(percentEncoded);
    } catch (e) {
      json = binary; // payload is not valid UTF-8 - fall back to the raw characters
    }
    return JSON.parse(json);
  } catch (e) {
    return null;
  }
};

// FastAPI returns `detail` as a string, as a list of validation errors (422) or as an object.
const formatApiDetail = (detail, status) => {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map(item => {
      if (typeof item === 'string') return item;
      if (!item || typeof item !== 'object') return String(item);
      const field = Array.isArray(item.loc) ? item.loc.filter(part => part !== 'body').join('.') : '';
      const message = item.msg || JSON.stringify(item);
      return field ? `${field}: ${message}` : message;
    });
    if (messages.length) return messages.join('; ');
  }
  if (detail && typeof detail === 'object') {
    if (typeof detail.message === 'string') {
      const quota = detail.quota;
      if (quota && quota.name) {
        // The quota object of plan A4: what was hit, against what, and when
        // it resets - the difference between information and an opaque 403.
        const unlimited = quota.limit === null || quota.limit === undefined;
        const limitText = unlimited ? 'unlimited' : `the limit of ${quota.limit}`;
        let text = `${detail.message} (${quota.name}: ${limitText}`;
        if (quota.used !== undefined && quota.used !== null) text += `, currently ${quota.used}`;
        if (quota.resets_at) text += `, resets at ${new Date(quota.resets_at).toLocaleString()}`;
        return text + ')';
      }
      return detail.message;
    }
    return JSON.stringify(detail);
  }
  return `HTTP error! status: ${status}`;
};

const humanizeKey = (value) =>
  String(value)
    .replace(/_/g, ' ')
    .replace(/\bllm\b/gi, 'LLM')
    .replace(/\b\w/g, char => char.toUpperCase());

// "3 min ago", with the exact time left to a tooltip.
const timeAgo = (iso) => {
  if (!iso) return '';
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 45) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} d ago`;
  return new Date(iso).toLocaleDateString();
};

const STATUS_LABELS = { queued: 'Queued', running: 'Running', completed: 'Completed', failed: 'Failed', cancelled: 'Cancelled' };
const STATUS_TONES = { completed: 'bg-ok', failed: 'bg-bad', running: 'bg-accent animate-pulse', queued: 'bg-faint', cancelled: 'bg-faint' };

// A status is a dot and a word: the word carries the meaning, the dot only helps scanning.
const StatusMark = ({ status }) => (
  <span className="inline-flex items-center gap-2">
    <span className={classNames('dot', STATUS_TONES[status])} aria-hidden="true" />
    <span>{STATUS_LABELS[status] || status}</span>
  </span>
);

const classNames = (...classes) => classes.filter(Boolean).join(' ');

// Fallbacks used when the training-modes endpoint cannot be reached.
const FALLBACK_TRAINING_MODES = ['manual', 'auto_tune', 'auto_fine_tune', 'llm_fine_tune', 'auto_search'];
const FALLBACK_MODE_DESCRIPTIONS = {
  manual: 'User-defined hyperparameters - full control over training settings',
  auto_tune: 'Randomized hyperparameter search over a curated per-model space',
  auto_fine_tune: 'Local hyperparameter search around the current configuration',
  llm_fine_tune: 'AI-guided parameters via Google Gemini (requires GOOGLE_API_KEY and the google-generativeai package)',
  auto_search: 'Model selection over multiple candidates - not Bayesian optimization',
};

// Fallback used when the training-presets endpoint cannot be reached.
const FALLBACK_TRAINING_PRESETS = [
  { name: 'conservative', description: 'Low learning rate, high regularization, fewer iterations' },
  { name: 'balanced', description: 'Default settings optimized for most use cases' },
  { name: 'aggressive', description: 'High learning rate, low regularization, more iterations' },
];

// Fallback used when the model catalog cannot be reached. Only the core
// estimator-backed models are listed, with the categories the form needs (a
// regression model has to be recognisable as one). The names match the backend
// catalog, so a run submitted from the fallback still trains on the server.
const FALLBACK_MODELS = [
  { name: 'Random_Forest', category: 'classification', description: 'Random Forest classifier for tabular data.', parameters: {}, optimization: [], test_results: null },
  { name: 'Logistic_Regression', category: 'classification', description: 'Logistic Regression classifier.', parameters: {}, optimization: [], test_results: null },
  { name: 'MLR', category: 'regression', description: 'Multiple Linear Regression for numeric prediction.', parameters: {}, optimization: [], test_results: null },
  { name: 'KNN', category: 'classification', description: 'K-Nearest Neighbors for classification or regression.', parameters: {}, optimization: [], test_results: null },
  { name: 'SVM', category: 'classification', description: 'Support Vector Machine for classification or regression.', parameters: {}, optimization: [], test_results: null },
  { name: 'XGboost_timeseries', category: 'time-series', description: 'XGBoost model for tabular and time-series prediction.', parameters: {}, optimization: [], test_results: null },
  { name: 'lightGBM_timeseries', category: 'time-series', description: 'LightGBM model for fast time-series and tabular training.', parameters: {}, optimization: [], test_results: null },
  { name: 'CATboost_timeseries', category: 'time-series', description: 'CatBoost model for robust time-series and tabular training.', parameters: {}, optimization: [], test_results: null },
];

// Model categories whose members are trained through the same estimator-backed path
// and therefore report comparable metrics. They are the pool the auto_search mode
// compares; the remaining categories have no like-for-like candidates.
const COMPARABLE_MODEL_CATEGORIES = ['classification', 'regression', 'time-series'];

// The label of a dataset in the select of the new-job form: the name, and a
// hint of where it comes from, so that the datasets of the repository and the
// uploaded ones can be told apart.
const datasetOptionLabel = (dataset) => {
  if (!dataset) return '';
  const parts = [dataset.name];
  if (dataset.source === 'builtin') parts.push('(built-in)');
  else if (dataset.source === 'upload') parts.push('(yours)');
  else parts.push('(folder)');
  return parts.join(' ');
};

// --- AUTH CONTEXT ---
const AuthContext = createContext(null);

const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(localStorage.getItem('prime_token'));
  const [user, setUser] = useState(token ? parseJwt(token) : null);
  // Why the last session ended. The reason has to outlive the logout: clearing the
  // token unmounts the view that would display it, so it is kept in the auth state
  // and rendered by the sign-in view.
  const [sessionNotice, setSessionNotice] = useState(null);

  const login = (newToken) => {
    localStorage.setItem('prime_token', newToken);
    setToken(newToken);
    setUser(parseJwt(newToken));
    setSessionNotice(null);
  };

  const logout = useCallback(() => {
    localStorage.removeItem('prime_token');
    setToken(null);
    setUser(null);
  }, []);

  const apiFetch = useCallback(async (endpoint, options = {}) => {
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    
    // Handle form data for OAuth2 login which requires application/x-www-form-urlencoded
    const isFormData = options.body instanceof URLSearchParams;
    if (isFormData) {
      delete headers['Content-Type']; // Let browser set it with boundary if it was FormData, but for URLSearchParams it's fine.
      headers['Content-Type'] = 'application/x-www-form-urlencoded';
    }
    // A file upload is sent as FormData: the browser has to set the content
    // type itself, because only it knows the boundary of the parts.
    const isMultipart = typeof FormData !== 'undefined' && options.body instanceof FormData;
    if (isMultipart) {
      delete headers['Content-Type'];
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      // The reason is stored before the logout: the logout unmounts the view that
      // would display it, so the message would be lost otherwise.
      if (token) setSessionNotice('Session expired. Please log in again.');
      logout();
      const error = new Error("Session expired. Please log in again.");
      error.status = 401;
      throw error;
    }
    
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      const error = new Error(formatApiDetail(errData && errData.detail, response.status));
      error.status = response.status;
      throw error;
    }
    
    // Artifact endpoint returns a file
    if (endpoint.endsWith('/artifact')) return response.blob();
    
    return response.json();
  }, [token, logout]);

  return (
    <AuthContext.Provider value={{ token, user, login, logout, apiFetch, sessionNotice }}>
      {children}
    </AuthContext.Provider>
  );
};

// --- COMPONENTS ---

// --- VIEWS ---

const AuthView = ({ mode, setMode }) => {
  const { login, apiFetch, sessionNotice } = useContext(AuthContext);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (mode === 'register') {
        await apiFetch('/api/v1/register', {
          method: 'POST',
          body: JSON.stringify({ username, password })
        });
        // Auto-login after register
      }

      const params = new URLSearchParams();
      params.append('username', username);
      params.append('password', password);

      const data = await apiFetch('/token', {
        method: 'POST',
        body: params
      });

      login(data.access_token);
    } catch (err) {
      setError(err.status === 409
        ? 'Username already taken. Please choose a different username.'
        : err.status === 429
        ? 'Too many attempts. Please wait a minute and try again.'
        : err.message);
    } finally {
      setLoading(false);
    }
  };

  const registering = mode === 'register';
  return (
    <main className="min-h-screen flex items-center px-6 py-12">
      <div className="w-full max-w-sm mx-auto">
        <p className="text-sm font-medium text-muted mb-10">PrimeTrade AutoML</p>
        <h1 className="mb-2">{registering ? 'Create an account' : 'Sign in'}</h1>
        <p className="text-muted mb-8">Train a model on your data, check it against a baseline, and use it.</p>
        {sessionNotice && <p role="status" className="notice mb-5">{sessionNotice}</p>}
        {error && <p role="alert" className="notice notice-bad mb-5">{error}</p>}
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label htmlFor="auth-username" className="block text-sm text-muted mb-1.5">Username</label>
            <input
              id="auth-username" type="text" required autoComplete="username"
              value={username} onChange={(e) => setUsername(e.target.value)}
              className="field"
            />
          </div>
          <div>
            <label htmlFor="auth-password" className="block text-sm text-muted mb-1.5">Password</label>
            <input
              id="auth-password" type="password" required
              autoComplete={registering ? 'new-password' : 'current-password'}
              minLength={registering ? 8 : undefined}
              value={password} onChange={(e) => setPassword(e.target.value)}
              className="field"
            />
            {registering && <p className="mt-1.5 text-sm text-faint">At least 8 characters.</p>}
          </div>
          <button type="submit" disabled={loading} className="btn btn-primary w-full">
            {loading ? (registering ? 'Creating account...' : 'Signing in...') : (registering ? 'Create account' : 'Sign in')}
          </button>
        </form>
        <p className="mt-8 text-sm text-muted">
          {registering ? 'Already have an account? ' : 'New here? '}
          <button onClick={() => setMode(registering ? 'login' : 'register')} className="link">
            {registering ? 'Sign in' : 'Create an account'}
          </button>
        </p>
      </div>
    </main>
  );
};

// The order and the names in which the catalog is shown.
const MODEL_GROUPS = [
  ['classification', 'Classification'],
  ['regression', 'Regression'],
  ['clustering', 'Clustering and projection'],
  ['time-series', 'Forecasting with boosted trees'],
  ['timeseries', 'Forecasting with neural networks'],
  ['reinforcement-learning', 'Reinforcement learning'],
  ['autoencoder', 'Autoencoders'],
  ['nlp', 'Text'],
  ['vision', 'Images'],
  ['graph', 'Graphs'],
];
const DATASET_KIND_LABELS = {
  tabular: 'A table (CSV)',
  timeseries: 'A time series (CSV)',
  graph: 'A graph (nodes and edges)',
  text: 'Text',
  text_pairs: 'Pairs of texts',
  image_folder: 'A folder of images, one subfolder per class',
};

// The models in the order and under the names of the catalog page.
const groupModels = (models) => {
  const known = new Set(MODEL_GROUPS.map(([c]) => c));
  const groups = MODEL_GROUPS
    .map(([category, label]) => [label, models.filter((m) => m.category === category)])
    .filter(([, rows]) => rows.length > 0);
  const other = models.filter((m) => !known.has(m.category));
  if (other.length > 0) groups.push(['Other', other]);
  return groups;
};

const ModelsCatalog = () => {
  const { apiFetch } = useContext(AuthContext);
  const [models, setModels] = useState([]);
  const [modelsError, setModelsError] = useState(null);

  useEffect(() => {
    apiFetch('/api/v1/ml/models')
      .then(data => {
        setModels(Array.isArray(data) ? data : []);
        setModelsError(null);
      })
      // A failed request is not an empty catalog: the built-in fallback list is
      // rendered instead and the reason is reported, so an outage is not
      // mistaken for "this server has no models".
      .catch(err => {
        setModels(FALLBACK_MODELS);
        setModelsError(err.message || 'Unknown error');
      });
  }, [apiFetch]);

  const [query, setQuery] = useState('');

  const expectedResult = (testResults) => {
    if (!testResults) return null;
    const pct = (range) => `${(range[0] * 100).toFixed(0)} to ${(range[1] * 100).toFixed(0)} %`;
    if (testResults.expected_accuracy) return `Accuracy ${pct(testResults.expected_accuracy)}`;
    if (testResults.expected_r2) return `R² ${pct(testResults.expected_r2)}`;
    if (testResults.expected_silhouette) return `Silhouette ${testResults.expected_silhouette[0].toFixed(2)} to ${testResults.expected_silhouette[1].toFixed(2)}`;
    return null;
  };

  // What a model asks of the server, in the words a user would use.
  const needsOf = (model) => {
    const needs = [];
    if (model.requires_gpu === true) needs.push('needs a GPU');
    else if (model.requires_gpu === 'recommended') needs.push('GPU recommended');
    if (model.downloads_checkpoint) needs.push('downloads pretrained weights');
    return needs.join(', ');
  };

  const visible = models.filter((m) => {
    const q = query.trim().toLowerCase();
    return !q || m.name.toLowerCase().includes(q) || (m.description || '').toLowerCase().includes(q);
  });
  const groups = MODEL_GROUPS
    .map(([category, label]) => [label, visible.filter((m) => m.category === category)])
    .filter(([, rows]) => rows.length > 0);
  const knownCategories = new Set(MODEL_GROUPS.map(([c]) => c));
  const other = visible.filter((m) => !knownCategories.has(m.category));
  if (other.length > 0) groups.push(['Other', other]);
  const runnable = models.filter((m) => m.implemented !== false && m.available !== false).length;

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="mb-1">Models</h1>
          <p className="text-muted">
            {models.length > 0 ? `${runnable} of ${models.length} can run on this server.` : 'What you can train, and what this server can run.'}
          </p>
        </div>
        <input
          type="search" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="Find a model" aria-label="Find a model" className="field max-w-xs"
        />
      </header>

      {modelsError && (
        <p role="alert" className="notice">
          The model list could not be loaded ({modelsError}). Showing the built-in list instead.
        </p>
      )}

      {groups.length === 0 && <p className="text-muted">No model matches that search.</p>}

      {groups.map(([label, rows]) => (
        <section key={label}>
          <h2 className="mb-2">{label}</h2>
          <ul className="border-t border-rule">
            {rows.map((model) => {
              const usable = model.implemented !== false && model.available !== false;
              const result = usable ? expectedResult(model.test_results) : null;
              const parameters = Object.entries(model.parameters || {});
              return (
                <li key={model.name} className="border-b border-rule/60">
                  <details className="group">
                    <summary className="flex items-baseline gap-4 py-3 cursor-pointer list-none [&::-webkit-details-marker]:hidden hover:bg-surface/60 -mx-2 px-2 rounded">
                      <span className="font-medium text-strong w-56 shrink-0 break-words">{model.name}</span>
                      <span className="text-muted flex-1 min-w-0 line-clamp-1 group-open:line-clamp-none">{model.description}</span>
                      <span className={classNames('text-sm shrink-0 text-right', usable ? 'text-faint' : 'text-warn')}>
                        {usable ? needsOf(model) : 'Not available here'}
                      </span>
                    </summary>
                    <div className="pb-5 pt-1 max-w-prose space-y-4">
                      {!usable && (
                        <p className="notice">
                          {model.implemented === false
                            ? 'This model is not implemented yet.'
                            : (model.unavailable_reason || 'This server cannot run it.')}
                        </p>
                      )}
                      <dl className="grid grid-cols-[9rem_1fr] gap-x-4 gap-y-2 text-sm">
                        {result && (<><dt className="text-muted">Typical result</dt><dd className="text-ink">{result}</dd></>)}
                        {usable && model.test_results?.typical_training_time_sec != null && (
                          <><dt className="text-muted">Typical time</dt><dd className="text-ink">about {model.test_results.typical_training_time_sec} s on small data</dd></>
                        )}
                        {usable && model.test_results?.best_for?.length > 0 && (
                          <><dt className="text-muted">Good for</dt><dd className="text-ink">{model.test_results.best_for.map((u) => u.replace(/_/g, ' ')).join(', ')}</dd></>
                        )}
                        {model.dataset_kind && (<><dt className="text-muted">Data</dt><dd className="text-ink">{DATASET_KIND_LABELS[model.dataset_kind] || model.dataset_kind}</dd></>)}
                        {needsOf(model) && (<><dt className="text-muted">Needs</dt><dd className="text-ink">{needsOf(model)}{model.min_memory_mb ? `, about ${(model.min_memory_mb / 1024).toFixed(model.min_memory_mb >= 10240 ? 0 : 1)} GB of memory` : ''}</dd></>)}
                        <dt className="text-muted">Parameters</dt>
                        <dd className="text-ink">
                          {parameters.length === 0 ? 'None to set.' : (
                            <span className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                              {parameters.map(([k, v]) => (
                                <React.Fragment key={k}><span className="text-muted">{k}</span><span className="tabular-nums break-all">{JSON.stringify(v)}</span></React.Fragment>
                              ))}
                            </span>
                          )}
                        </dd>
                      </dl>
                    </div>
                  </details>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
};

const RunsDashboard = ({ navigate }) => {
  const { apiFetch } = useContext(AuthContext);
  const [runs, setRuns] = useState([]);
  const [runsError, setRunsError] = useState(null);
  // The runs ticked for a comparison (at most four: more would not fit a screen).
  const [selected, setSelected] = useState([]);
  const toggleSelected = (id) => setSelected((current) => (
    current.includes(id) ? current.filter((x) => x !== id) : (current.length < 4 ? [...current, id] : current)
  ));

  const fetchRuns = useCallback(() => {
    // A failed request is not the same as "there are no runs": the two cases are
    // reported separately so a backend outage is not mistaken for an empty history.
    apiFetch('/api/v1/ml/runs')
      .then(data => { setRuns(Array.isArray(data) ? data : []); setRunsError(null); })
      .catch(err => { setRunsError(err.message || 'Unknown error'); });
  }, [apiFetch]);

  useEffect(() => {
    fetchRuns();
    // Aggressive polling to maintain accurate state
    const interval = setInterval(fetchRuns, 5000);
    return () => clearInterval(interval);
  }, [fetchRuns]);

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="mb-1">Runs</h1>
          <p className="text-muted">Every training you started, and how it did against doing nothing.</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('compare', selected)}
            disabled={selected.length < 2}
            title="Tick two to four completed runs"
            className="btn btn-quiet"
          >
            Compare{selected.length > 0 ? ` (${selected.length})` : ''}
          </button>
          <button onClick={() => navigate('new-job')} className="btn btn-primary">New run</button>
        </div>
      </header>

      {runsError && (
        <p role="alert" className="notice notice-bad">The runs could not be loaded ({runsError}).</p>
      )}

      {runs.length === 0 && !runsError ? (
        <div className="panel max-w-prose">
          <h2 className="mb-1">No runs yet</h2>
          <p className="text-muted mb-4">Pick a dataset and a model, and the first result appears here with its baseline.</p>
          <button onClick={() => navigate('new-job')} className="btn btn-primary">Start a run</button>
        </div>
      ) : (
        <div className="overflow-x-auto -mx-3">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="th w-8"><span className="sr-only">Compare</span></th>
                <th className="th">Model</th>
                <th className="th">Dataset</th>
                <th className="th">Status</th>
                <th className="th">Result</th>
                <th className="th text-right">Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const result = resultOf(run);
                return (
                  <tr key={run.id} onClick={() => navigate('run-details', run.id)} className="cursor-pointer hover:bg-surface/70">
                    <td className="td" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        aria-label={`Select run ${run.id} for a comparison`}
                        checked={selected.includes(run.id)}
                        onChange={() => toggleSelected(run.id)}
                        disabled={run.status !== 'completed'}
                        className="accent-[rgb(var(--accent))]"
                      />
                    </td>
                    <td className="td">
                      <span className="inline-flex items-baseline gap-2 whitespace-nowrap">
                        <a
                          href={`#/run-details/${run.id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="font-medium text-strong hover:text-accent"
                        >
                          {run.model_name}
                        </a>
                        <span className="text-faint tabular-nums">#{run.id}</span>
                      </span>
                    </td>
                    <td className="td text-muted"><span className="block truncate max-w-[14rem]">{run.dataset_tag}</span></td>
                    <td className="td"><StatusMark status={run.status} /></td>
                    <td className="td tabular-nums">
                      {result ? (
                        <>
                          <span className="text-strong">{result.text}</span>
                          {result.baseline && <span className="text-faint ml-2">baseline {result.baseline}</span>}
                          {result.beatsBaseline === false && (
                            <span className={classNames('ml-2', result.worse ? 'text-warn' : 'text-faint')}>
                              {result.worse ? 'below baseline' : 'tied with baseline'}
                            </span>
                          )}
                        </>
                      ) : <span className="text-faint">{run.status === 'completed' ? 'No score' : ''}</span>}
                    </td>
                    <td className="td text-right text-muted whitespace-nowrap" title={new Date(run.created_at).toLocaleString()}>
                      {timeAgo(run.created_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

// --- METRICS, EVALUATION AND PREDICTION ---------------------------------------

// Metrics for which a smaller value is the better one.
const LOWER_IS_BETTER = new Set(['mse', 'rmse', 'mae', 'smape', 'mase', 'reconstruction_mse', 'held_out_perplexity', 'davies_bouldin', 'train_loss']);
// The numbers of a run that are scores. Only those can be "the best": a larger
// training set or a higher baseline is not better.
const SCORE_METRICS = new Set([
  'accuracy', 'val_accuracy', 'balanced_accuracy', 'f1_macro', 'precision_macro', 'recall_macro', 'roc_auc',
  'r2', 'mae', 'rmse', 'mse', 'smape', 'mase', 'rouge1', 'rouge2', 'rougeL', 'held_out_perplexity',
  'reconstruction_mse', 'reconstruction_r2', 'mean_return', 'success_rate', 'silhouette', 'davies_bouldin',
  'calinski_harabasz', 'trustworthiness', 'explained_variance', 'skill_vs_naive',
]);
// Metrics that are not a single number: they get a panel of their own instead
// of a tile (a tile would print "[object Object]").
const STRUCTURED_METRICS = new Set([
  'model_parameters', 'cv', 'confusion_matrix', 'preprocessing', 'search_results',
]);
const isNumber = (v) => typeof v === 'number' && Number.isFinite(v);

const formatMetric = (val) => {
  if (val === null || val === undefined) return '—';
  if (typeof val === 'boolean') return val ? 'yes' : 'no';
  if (typeof val === 'number') return Number.isInteger(val) ? String(val) : fmtNum(val);
  return String(val);
};

// What the list shows for a run: the score, and the baseline it has to beat.
// ``beatsBaseline`` is null when the run has no baseline to compare with.
const resultOf = (run) => {
  if (!run.metrics || run.status !== 'completed') return null;
  const h = headlineOf(run.metrics);
  if (!h) return null;
  const hasBase = isNumber(h.baseline);
  const margin = h.fraction ? 0.01 : 0;
  const beats = hasBase ? (h.higherBetter ? h.value > h.baseline + margin : h.value < h.baseline) : null;
  // "Tied" is within the margin; "below" is clearly worse than doing nothing.
  const worse = hasBase && (h.higherBetter ? h.value < h.baseline - margin : h.value > h.baseline + margin);
  return {
    text: `${h.label.replace('Accuracy on held-out images', 'Accuracy').replace('Perplexity on held-out text', 'Perplexity')} ${fmtNum(h.value)}`,
    baseline: hasBase ? fmtNum(h.baseline) : null,
    beatsBaseline: beats,
    worse: !!worse,
  };
};

// Numbers are shown with the precision that means something for their size.
const fmtNum = (v) => {
  if (!isNumber(v)) return '—';
  const abs = Math.abs(v);
  if (abs >= 1000) return v.toFixed(0);
  if (abs >= 100) return v.toFixed(1);
  if (abs >= 0.01 || abs === 0) return v.toFixed(3);
  return v.toFixed(4);
};

// Every kind of run reports one number that matters and the number a model that
// learned nothing would score. This finds the pair, whatever the trainer calls it,
// so one component can answer the question the product exists for: is it better
// than doing nothing?
const headlineOf = (m) => {
  if (!m) return null;
  const pick = (candidates, higherBetter) => {
    const present = candidates.filter(([key]) => isNumber(m[key]));
    if (present.length === 0) return null;
    // The strongest baseline is the one that has to be beaten.
    present.sort((x, y) => (higherBetter ? m[y[0]] - m[x[0]] : m[x[0]] - m[y[0]]));
    return { value: m[present[0][0]], phrase: present[0][1] };
  };
  const make = (key, label, higherBetter, baselines, fraction = false, cvKey = null) => {
    if (!isNumber(m[key])) return null;
    const base = pick(baselines, higherBetter);
    return { key, label, value: m[key], higherBetter, fraction, cvKey, baseline: base ? base.value : null, phrase: base ? base.phrase : null };
  };
  const NAIVE = [['baseline_seasonal_naive_mae', 'repeating the last season'], ['baseline_naive_mae', 'repeating the last value']];
  const MAJORITY = 'always predicting the most frequent class';
  return (
    make('mean_return', 'Average return', true, [['baseline_mean_return', 'a random policy']]) ||
    make('held_out_perplexity', 'Perplexity on held-out text', false, [['pretrained_perplexity', 'the same model before fine-tuning'], ['unigram_perplexity', 'a model that only counts words']]) ||
    make('rouge1', 'ROUGE-1', true, [['baseline_copy_rouge1', 'copying the input']], true) ||
    make('mae', 'Mean absolute error', false, NAIVE, false, 'mae') ||
    make('val_accuracy', 'Accuracy on held-out images', true, [['baseline_accuracy', MAJORITY]], true) ||
    make('accuracy', 'Accuracy', true, [
      ['baseline_feature_only_accuracy', 'a model that ignores the graph'],
      ['baseline_majority_accuracy', MAJORITY],
      ['baseline_accuracy', MAJORITY],
    ], true, 'accuracy') ||
    make('rmse', 'Root mean squared error', false, [['baseline_rmse', 'always predicting the training mean']], false, 'rmse') ||
    make('reconstruction_mse', 'Reconstruction error', false, [['baseline_mse', 'rebuilding every column as its mean']]) ||
    null
  );
};

// The one bold element of the product: the result drawn against the baseline.
// A hairline scale; a tick where doing nothing lands; the model's score as a
// dot with a segment back to the tick (blue when it is better, amber when it
// is not); and the cross-validation range as a faint band, so the spread of
// the score is visible next to the score.
const ResultLine = ({ metrics }) => {
  const h = headlineOf(metrics);
  if (!h) return null;
  const hasBase = isNumber(h.baseline);
  const cv = metrics.cv && metrics.cv.scores && h.cvKey ? metrics.cv.scores[h.cvKey] : null;

  const points = [h.value, ...(hasBase ? [h.baseline] : []), ...(cv ? [cv.mean - cv.std, cv.mean + cv.std] : [])];
  let lo = h.fraction ? 0 : Math.min(0, ...points);
  let hi = h.fraction ? 1 : Math.max(0, ...points);
  if (!h.fraction) {
    const pad = (hi - lo || 1) * 0.08;
    hi += pad;
    if (lo < 0) lo -= pad;
  }
  const at = (v) => Math.max(0, Math.min(100, ((v - lo) / (hi - lo || 1)) * 100));

  const margin = h.fraction ? 0.01 : 0;
  const better = hasBase ? (h.higherBetter ? h.value > h.baseline + margin : h.value < h.baseline) : null;

  let sentence = null;
  if (hasBase) {
    if (h.higherBetter && h.fraction) {
      const points100 = (h.value - h.baseline) * 100;
      sentence = Math.abs(points100) < 1
        ? `About the same as ${h.phrase} (${fmtNum(h.baseline)}).`
        : `${Math.abs(points100).toFixed(1)} points ${points100 > 0 ? 'better' : 'worse'} than ${h.phrase} (${fmtNum(h.baseline)}).`;
    } else if (h.higherBetter) {
      const diff = h.value - h.baseline;
      sentence = diff === 0
        ? `The same as ${h.phrase} (${fmtNum(h.baseline)}).`
        : `${fmtNum(Math.abs(diff))} ${diff > 0 ? 'higher' : 'lower'} than ${h.phrase} (${fmtNum(h.baseline)}).`;
    } else {
      const pct = h.baseline !== 0 ? (1 - h.value / h.baseline) * 100 : 0;
      sentence = Math.abs(pct) < 1
        ? `About the same as ${h.phrase} (${fmtNum(h.baseline)}).`
        : `${Math.abs(pct).toFixed(0)} % ${pct > 0 ? 'lower' : 'higher'} than ${h.phrase} (${fmtNum(h.baseline)}).`;
    }
    if (better === false) {
      const worse = h.higherBetter ? h.value < h.baseline - margin : h.value > h.baseline;
      // "About the same" already says it; only a model that is clearly worse needs the verdict first.
      sentence = worse ? `Worse than ${h.phrase}. ${sentence}` : `No better than ${h.phrase} (${fmtNum(h.baseline)}).`;
    }
  }

  const tickLeft = hasBase ? Math.min(92, Math.max(8, at(h.baseline))) : 0;
  const segStart = hasBase ? Math.min(at(h.baseline), at(h.value)) : 0;
  const segEnd = hasBase ? Math.max(at(h.baseline), at(h.value)) : 0;
  const description = `${h.label} ${fmtNum(h.value)}${hasBase ? `, baseline ${fmtNum(h.baseline)}` : ''}${cv ? `, cross-validation ${fmtNum(cv.mean)} plus or minus ${fmtNum(cv.std)}` : ''}.`;

  return (
    <section aria-label="Result" className="panel">
      <div className="flex flex-wrap items-baseline gap-x-4">
        <span className="text-5xl font-semibold text-strong tabular-nums tracking-tight">{fmtNum(h.value)}</span>
        <span className="text-muted">{h.label}{h.higherBetter ? '' : ', lower is better'}</span>
      </div>
      {sentence && <p className={classNames('mt-2', better === false ? 'text-warn' : 'text-ink')}>{sentence}</p>}

      {hasBase && (
        <div className="relative mt-12 mb-1 h-5" role="img" aria-label={description}>
          <div className="absolute left-0 right-0 top-1/2 h-px bg-rule" />
          {cv && (
            <div
              className="absolute top-1/2 -translate-y-1/2 h-2 rounded-sm bg-accent/25"
              style={{ left: `${at(cv.mean - cv.std)}%`, width: `${Math.max(0.5, at(cv.mean + cv.std) - at(cv.mean - cv.std))}%` }}
            />
          )}
          <div
            className={classNames('absolute top-1/2 -translate-y-1/2 h-0.5', better === false ? 'bg-warn' : 'bg-accent')}
            style={{ left: `${segStart}%`, width: `${segEnd - segStart}%` }}
          />
          <div className="absolute top-0 bottom-0 w-px bg-muted" style={{ left: `${at(h.baseline)}%` }} />
          <span className="absolute bottom-full mb-1.5 text-xs text-muted whitespace-nowrap -translate-x-1/2 tabular-nums" style={{ left: `${tickLeft}%` }}>
            baseline {fmtNum(h.baseline)}
          </span>
          <div
            className={classNames('absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 rounded-full ring-4 ring-canvas', better === false ? 'bg-warn' : 'bg-accent')}
            style={{ left: `${at(h.value)}%` }}
          />
        </div>
      )}
      {hasBase && (
        <div className="flex justify-between text-xs text-faint tabular-nums mt-3">
          <span>{fmtNum(lo)}</span>
          <span>{fmtNum(hi)}</span>
        </div>
      )}
      {cv && cv.mean !== undefined && (
        <p className="mt-4 text-sm text-muted tabular-nums">
          Cross-validation on the training rows: {fmtNum(cv.mean)} ± {fmtNum(cv.std)}
          {metrics.cv.folds ? ` over ${metrics.cv.folds} folds` : ''}, drawn as the band on the line.
        </p>
      )}
      {metrics.cv && !metrics.cv.scores && metrics.cv.skipped && (
        <p className="mt-4 text-sm text-faint">Cross-validation did not run: {metrics.cv.skipped}.</p>
      )}
    </section>
  );
};

// Scores that explain the headline, shown only when the run reports them.
const OTHER_SCORES = [
  ['balanced_accuracy', 'Balanced accuracy'], ['f1_macro', 'F1 (macro)'], ['roc_auc', 'ROC AUC'],
  ['r2', 'R²'], ['mae', 'MAE'], ['rmse', 'RMSE'], ['smape', 'sMAPE %'], ['rouge2', 'ROUGE-2'], ['rougeL', 'ROUGE-L'],
  ['skill_vs_naive', 'Skill vs naive'], ['mean_return', 'Average return'], ['success_rate', 'Success rate'],
];

const EvaluationPanel = ({ metrics }) => {
  const headline = headlineOf(metrics);
  const shown = OTHER_SCORES.filter(([key]) => isNumber(metrics[key]) && !(headline && headline.key === key));
  return (
    <>
      <ResultLine metrics={metrics} />
      {shown.length > 0 && (
        <section className="panel">
          <h2 className="mb-4">Other scores</h2>
          <dl className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-x-8 gap-y-5">
            {shown.map(([key, label]) => (
              <div key={key}>
                <dt className="text-sm text-muted">{label}</dt>
                <dd className="text-lg text-strong tabular-nums">{fmtNum(metrics[key])}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
    </>
  );
};

const Bar = ({ label, value, max, tone = 'bg-accent', note }) => {
  const width = isNumber(value) && max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div>
      <div className="flex justify-between text-sm text-muted mb-1">
        <span>{label}</span>
        <span className="tabular-nums text-ink">{formatMetric(value)}{note ? ` ${note}` : ''}</span>
      </div>
      <div className="h-1.5 bg-raised rounded-full">
        <div className={`h-1.5 rounded-full ${tone}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
};

const ConfusionMatrix = ({ confusion }) => {
  if (!confusion || !Array.isArray(confusion.matrix) || confusion.matrix.length === 0) return null;
  const labels = confusion.labels || [];
  const top = Math.max(1, ...confusion.matrix.flat());
  return (
    <section className="panel">
      <h2 className="mb-1">Where it gets confused</h2>
      <p className="text-sm text-muted mb-5">Rows are the true class, columns the predicted one. The diagonal is correct.</p>
      <div className="overflow-x-auto">
        <table className="text-sm text-center">
          <thead>
            <tr>
              <th className="px-3 py-2" />
              {labels.map((l) => <th key={String(l)} scope="col" className="px-3 py-2 text-muted font-medium">{String(l)}</th>)}
            </tr>
          </thead>
          <tbody>
            {confusion.matrix.map((row, i) => (
              <tr key={i}>
                <th scope="row" className="px-3 py-2 text-muted font-medium text-right">{String(labels[i])}</th>
                {row.map((count, j) => (
                  <td
                    key={j}
                    className={classNames('px-4 py-2 tabular-nums rounded-sm', i === j ? 'text-strong' : 'text-ink')}
                    style={{ background: `rgb(var(${i === j ? '--accent' : '--warn'}) / ${count === 0 ? 0 : 0.12 + (count / top) * 0.4})` }}
                  >
                    {count}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};

// What was done to the data before the model saw it.
const PreprocessingReport = ({ report }) => {
  if (!report) return null;
  const list = (items) => (items && items.length ? items.join(', ') : 'none');
  return (
    <section className="panel">
      <h2 className="mb-4">How the data was prepared</h2>
      <dl className="grid grid-cols-[13rem_1fr] gap-x-6 gap-y-3 max-w-prose">
        <dt className="text-muted">Number columns</dt><dd className="break-words">{list(report.numeric_columns)}</dd>
        <dt className="text-muted">Text columns, one-hot encoded</dt><dd className="break-words">{list(report.categorical_columns)}</dd>
        <dt className="text-muted">Missing values filled in</dt><dd className="tabular-nums">{report.missing_cells_imputed}</dd>
        <dt className="text-muted">Rows without a label, dropped</dt><dd className="tabular-nums">{report.rows_dropped_missing_label}</dd>
        <dt className="text-muted">Numbers standardised</dt><dd>{formatMetric(report.scaled)}</dd>
        <dt className="text-muted">Task type</dt><dd>{report.task_type_source === 'request' ? 'chosen by you' : 'guessed from the label'}</dd>
      </dl>
      {report.dropped_columns && report.dropped_columns.length > 0 && (
        <div className="mt-5 max-w-prose">
          <h3 className="mb-2">Columns left out</h3>
          <ul className="space-y-1">
            {report.dropped_columns.map((d) => (
              <li key={d.column} className="notice"><span className="text-strong">{d.column}</span>: {d.reason}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
};

// Asking a model: the form is built from the schema of the run, so nobody has
// to know the columns by heart. What a model takes depends on its kind, and the
// server says which in ``request_kind``: a table row, some texts, a prompt, the
// last window of a series, node ids, the state of an agent, or an image.
const PredictPanel = ({ runId }) => {
  const { apiFetch } = useContext(AuthContext);
  const [schema, setSchema] = useState(null);
  const [schemaError, setSchemaError] = useState(null);
  const [values, setValues] = useState({});          // the row form
  const [mode, setMode] = useState('form');          // row form or JSON
  const [text, setText] = useState('');              // texts, prompt, node ids, state, window
  const [maxTokens, setMaxTokens] = useState(64);
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    setSchema(null); setSchemaError(null); setResult(null); setError(null);
    apiFetch(`/api/v1/ml/runs/${runId}/schema`)
      .then((s) => {
        if (!active) return;
        setSchema(s);
        const kind = s.request_kind || 'rows';
        if (kind === 'rows') {
          const initial = {};
          (s.features || []).forEach((f) => { initial[f.name] = f.default === undefined ? '' : String(f.default); });
          setValues(initial);
          setText(JSON.stringify([Object.fromEntries((s.features || []).map((f) => [f.name, f.default]))], null, 2));
        } else if (kind === 'window_rows') {
          // One line per time step, columns separated by commas: the target first, then the covariates.
          const columns = (s.features || []).length || 1;
          setText(Array.from({ length: s.window || 1 }, () => Array(columns).fill('0').join(', ')).join('\n'));
        } else if (kind === 'state') {
          setText('0');
        } else {
          setText('');
        }
      })
      .catch((err) => { if (active) setSchemaError(err.message || 'This model cannot predict.'); });
    return () => { active = false; };
  }, [apiFetch, runId]);

  const body = () => {
    const kind = schema.request_kind || 'rows';
    if (kind === 'rows') {
      if (mode === 'json') {
        const rows = JSON.parse(text);
        if (!Array.isArray(rows)) throw new Error('The rows have to be a JSON array of objects.');
        return { rows };
      }
      const row = {};
      (schema.features || []).forEach((f) => {
        const raw = values[f.name];
        if (raw === '' || raw === undefined) return; // left out: the model fills it in as in training
        row[f.name] = f.kind === 'numeric' ? Number(raw) : raw;
      });
      return { rows: [row] };
    }
    if (kind === 'texts') {
      const texts = text.split('\n').map((t) => t.trim()).filter(Boolean);
      if (texts.length === 0) throw new Error('Write at least one text, one per line.');
      return { texts };
    }
    if (kind === 'prompt') {
      if (!text.trim()) throw new Error('Write a prompt.');
      return { prompt: text, max_new_tokens: Number(maxTokens) || 64 };
    }
    if (kind === 'window_rows') {
      const window_rows = text.split('\n').map((l) => l.trim()).filter(Boolean)
        .map((l) => l.split(/[,\s]+/).filter(Boolean).map(Number));
      if (window_rows.some((r) => r.some((v) => Number.isNaN(v)))) throw new Error('Every value has to be a number.');
      return { window_rows };
    }
    if (kind === 'node_ids') {
      const node_ids = text.split(/[,\s]+/).filter(Boolean);
      if (node_ids.length === 0) throw new Error('Give at least one node id.');
      return { node_ids };
    }
    if (kind === 'state') {
      const t = text.trim();
      if (!t) throw new Error('Give a state.');
      // A table agent takes one whole number; a policy takes the observation vector.
      return { state: /[,\s]/.test(t) ? t.split(/[,\s]+/).filter(Boolean).map(Number) : Number(t) };
    }
    throw new Error(`The interface does not know the request kind "${kind}".`);
  };

  const predict = async () => {
    setLoading(true); setError(null); setResult(null);
    try {
      if ((schema.request_kind || 'rows') === 'image') {
        if (!file) throw new Error('Choose an image first.');
        const form = new FormData();
        form.append('file', file);
        setResult(await apiFetch(`/api/v1/ml/runs/${runId}/predict-image`, { method: 'POST', body: form }));
      } else {
        setResult(await apiFetch(`/api/v1/ml/runs/${runId}/predict`, { method: 'POST', body: JSON.stringify(body()) }));
      }
    } catch (err) {
      setError(err.message || 'The prediction failed.');
    } finally {
      setLoading(false);
    }
  };

  if (schemaError) {
    return (
      <section className="panel">
        <h2 className="mb-2">Use this model</h2>
        <p className="text-muted">{schemaError}</p>
      </section>
    );
  }
  if (!schema) return <section className="panel"><p className="text-muted">Loading the model...</p></section>;

  const kind = schema.request_kind || 'rows';
  const hints = {
    texts: 'One text per line.',
    prompt: 'The model continues this text.',
    window_rows: `Exactly ${schema.window} lines, oldest first. Each line: ${(schema.features || []).join(', ') || 'the value'}.`,
    node_ids: `Node ids from the graph, separated by commas or spaces (${schema.nodes ?? '?'} nodes).`,
    state: schema.n_states != null ? `A state from 0 to ${schema.n_states - 1} (${schema.n_actions} actions).` : 'The observation: numbers separated by commas.',
    image: `An image of one of: ${(schema.classes || []).join(', ')}.`,
  };

  return (
    <section className="panel">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-1">
        <h2 className="whitespace-nowrap">Use this model</h2>
        {kind === 'rows' && (
          <div className="inline-flex text-sm border border-rule rounded-md overflow-hidden" role="group" aria-label="Input style">
            {[['form', 'One row'], ['json', 'Several rows']].map(([m, label]) => (
              <button key={m} onClick={() => setMode(m)} aria-pressed={mode === m}
                className={classNames('px-3 h-8 inline-flex items-center', mode === m ? 'bg-raised text-strong' : 'text-muted hover:text-strong')}>
                {label}
              </button>
            ))}
          </div>
        )}
      </div>
      {schema.output && <p className="text-sm text-muted mb-5">{schema.output.charAt(0).toUpperCase() + schema.output.slice(1)}.</p>}

      {kind === 'rows' && mode === 'form' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
          {(schema.features || []).map((f) => (
            <div key={f.name}>
              <label htmlFor={`f-${f.name}`} className="block text-sm text-muted mb-1">
                {f.name}
                {f.kind === 'numeric' && <span className="text-faint tabular-nums">{` (${formatMetric(f.min)} to ${formatMetric(f.max)})`}</span>}
              </label>
              {f.kind === 'categorical' && !f.categories_truncated ? (
                <select id={`f-${f.name}`} value={values[f.name] ?? ''} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })} className="field">
                  <option value="">(missing)</option>
                  {f.categories.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              ) : (
                <input id={`f-${f.name}`} type={f.kind === 'numeric' ? 'number' : 'text'} step="any"
                  value={values[f.name] ?? ''} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })} className="field" />
              )}
            </div>
          ))}
        </div>
      )}
      {kind === 'rows' && mode === 'json' && (
        <textarea aria-label="Rows as JSON" value={text} onChange={(e) => setText(e.target.value)} rows={8} className="field font-mono text-sm" />
      )}

      {['texts', 'prompt', 'window_rows', 'node_ids'].includes(kind) && (
        <div>
          <label htmlFor="predict-input" className="block text-sm text-muted mb-1">{hints[kind]}</label>
          <textarea id="predict-input" value={text} onChange={(e) => setText(e.target.value)}
            rows={kind === 'node_ids' ? 2 : 5} className={classNames('field', kind === 'window_rows' && 'font-mono text-sm')} />
        </div>
      )}
      {kind === 'prompt' && (
        <div className="mt-3 max-w-[12rem]">
          <label htmlFor="max-tokens" className="block text-sm text-muted mb-1">Longest answer, in tokens</label>
          <input id="max-tokens" type="number" min="1" max="512" value={maxTokens} onChange={(e) => setMaxTokens(e.target.value)} className="field" />
        </div>
      )}
      {kind === 'state' && (
        <div className="max-w-sm">
          <label htmlFor="predict-state" className="block text-sm text-muted mb-1">{hints.state}</label>
          <input id="predict-state" type="text" value={text} onChange={(e) => setText(e.target.value)} className="field" />
        </div>
      )}
      {kind === 'image' && (
        <div>
          <label htmlFor="predict-image" className="block text-sm text-muted mb-1">{hints.image}</label>
          <input id="predict-image" type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="block text-sm text-muted file:mr-4 file:btn file:btn-quiet file:cursor-pointer" />
        </div>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-4">
        <button onClick={predict} disabled={loading} className="btn btn-primary">{loading ? 'Working...' : (kind === 'prompt' ? 'Generate' : 'Predict')}</button>
        {kind === 'rows' && <span className="text-sm text-faint">A field left empty is treated as missing, as in training.</span>}
      </div>

      {error && <p role="alert" className="notice notice-bad mt-5 whitespace-pre-wrap">{error}</p>}
      {result && <PredictionResult result={result} />}
    </section>
  );
};

const PredictionResult = ({ result }) => {
  const predictions = result.predictions || [];
  return (
    <div className="mt-6 space-y-5" aria-live="polite">
      {result.warnings && result.warnings.length > 0 && (
        <ul className="space-y-1">{result.warnings.map((w, i) => <li key={i} className="notice">{w}</li>)}</ul>
      )}

      {typeof result.text === 'string' && (
        <div>
          <p className="text-sm text-muted mb-1">
            Generated{result.new_tokens != null ? `, ${result.new_tokens} tokens` : ''}
          </p>
          <p className="text-ink whitespace-pre-wrap border-l-2 border-accent pl-4">{result.text}</p>
        </div>
      )}

      {result.action !== undefined && (
        <div>
          <p className="text-sm text-muted mb-1">Best action</p>
          <p className="text-4xl font-semibold text-strong tabular-nums">{Array.isArray(result.action) ? result.action.join(', ') : String(result.action)}</p>
          {result.q_values && (
            <p className="mt-2 text-sm text-muted tabular-nums">Value of each action: {result.q_values.map((v) => formatMetric(v)).join(', ')}</p>
          )}
        </div>
      )}

      {predictions.map((p, i) => (
        <div key={i} className={classNames(i > 0 && 'border-t border-rule/60 pt-5')}>
          {predictions.length > 1 && <p className="text-sm text-muted mb-1">Row {i + 1}</p>}
          <p className="text-3xl font-semibold text-strong tabular-nums break-words">
            {Array.isArray(p) ? p.join(', ') : (isNumber(p) ? formatMetric(p) : String(p))}
          </p>
          {result.probabilities && result.probabilities[i] && (
            <div className="mt-4 space-y-2 max-w-md">
              {Object.entries(result.probabilities[i]).map(([label, prob]) => (
                <Bar key={label} label={String(label)} value={prob} max={1} tone={String(label) === String(p) ? 'bg-accent' : 'bg-faint'} />
              ))}
            </div>
          )}
        </div>
      ))}

      {result.reconstruction_error && result.reconstruction_error.map((err, i) => (
        <div key={i}>
          <p className={classNames('text-2xl font-semibold tabular-nums', result.is_anomaly[i] ? 'text-bad' : 'text-ok')}>
            {result.is_anomaly[i] ? 'Unusual' : 'Usual'}, error {formatMetric(err)}
          </p>
          <p className="text-sm text-muted tabular-nums mt-1">Threshold {formatMetric(result.threshold)}. Latent code {result.latent[i].map((v) => v.toFixed(3)).join(', ')}.</p>
        </div>
      ))}
    </div>
  );
};

// Several runs side by side: the same metric in a row, the best value marked,
// and a bar so the difference is visible without reading the numbers.
const CompareRuns = ({ runIds, navigate }) => {
  const { apiFetch } = useContext(AuthContext);
  const [runs, setRuns] = useState(null);
  const [error, setError] = useState(null);
  const [metric, setMetric] = useState(null);
  const ids = Array.isArray(runIds) ? runIds : [];

  useEffect(() => {
    let active = true;
    Promise.all(ids.map((id) => apiFetch(`/api/v1/ml/runs/${id}`)))
      .then((data) => { if (active) setRuns(data); })
      .catch((err) => { if (active) setError(err.message || 'Could not load the runs.'); });
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiFetch, ids.join(',')]);

  if (error) return <p role="alert" className="notice notice-bad">{error}</p>;
  if (!runs) return <p className="text-muted">Loading the runs...</p>;

  const completed = runs.filter((r) => r.status === 'completed' && r.metrics);
  const metricNames = [];
  completed.forEach((r) => Object.entries(r.metrics).forEach(([k, v]) => {
    if (isNumber(v) && !STRUCTURED_METRICS.has(k) && !k.startsWith('_') && !metricNames.includes(k)) metricNames.push(k);
  }));
  const chartable = metricNames.filter((n) => SCORE_METRICS.has(n));
  const choices = chartable.length > 0 ? chartable : metricNames;
  const selected = metric && choices.includes(metric) ? metric : choices[0];
  const valueOf = (run, name) => (run.metrics && isNumber(run.metrics[name]) ? run.metrics[name] : null);
  const bestOf = (name) => {
    if (!SCORE_METRICS.has(name)) return null;
    const values = completed.map((r) => valueOf(r, name)).filter((v) => v !== null);
    if (values.length < 2) return null;
    return LOWER_IS_BETTER.has(name) ? Math.min(...values) : Math.max(...values);
  };
  const top = selected ? Math.max(1e-12, ...completed.map((r) => Math.abs(valueOf(r, selected) || 0))) : 1;
  // Scores of runs on different data cannot be ranked against each other.
  const datasets = [...new Set(runs.map((r) => r.dataset_tag).filter(Boolean))];

  return (
    <div className="space-y-10">
      <nav aria-label="Breadcrumb" className="text-sm text-muted">
        <a href="#/runs" className="hover:text-strong">Runs</a>
        <span className="mx-2 text-faint" aria-hidden="true">/</span>
        <span>Compare</span>
      </nav>

      <header className="-mt-5">
        <h1 className="mb-1">Compare {runs.length} runs</h1>
        <p className="text-muted">The same score side by side. The best value in each row is marked.</p>
      </header>

      {datasets.length > 1 && (
        <p role="status" className="notice">
          These runs used different datasets ({datasets.join(', ')}), so their scores are not directly comparable.
        </p>
      )}
      {completed.length < runs.length && (
        <p role="status" className="notice">
          {runs.length - completed.length} of the selected runs {runs.length - completed.length === 1 ? 'has' : 'have'} no result yet, so {runs.length - completed.length === 1 ? 'it is' : 'they are'} left out.
        </p>
      )}

      {selected && (
        <section className="panel">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
            <h2>By metric</h2>
            <label className="flex items-center gap-3 text-sm text-muted">
              Metric
              <select value={selected} onChange={(e) => setMetric(e.target.value)} className="field w-auto">
                {choices.map((n) => <option key={n} value={n}>{n.replace(/_/g, ' ')}</option>)}
              </select>
            </label>
          </div>
          <div className="space-y-4 max-w-2xl">
            {completed.map((r) => (
              <Bar
                key={r.id}
                label={`#${r.id} ${r.model_name}`}
                value={valueOf(r, selected)}
                max={top}
                tone={valueOf(r, selected) !== null && valueOf(r, selected) === bestOf(selected) ? 'bg-accent' : 'bg-faint'}
              />
            ))}
          </div>
          <p className="text-sm text-faint mt-4">{LOWER_IS_BETTER.has(selected) ? 'Lower is better.' : 'Higher is better.'}</p>
        </section>
      )}

      <section className="panel overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="th">Metric</th>
              {completed.map((r) => (
                <th key={r.id} className="th">
                  <button onClick={() => navigate('run-details', r.id)} className="text-strong hover:text-accent font-medium">
                    {r.model_name}
                  </button>
                  <span className="text-faint ml-2">#{r.id}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metricNames.map((name) => (
              <tr key={name}>
                <th scope="row" className="td text-left font-normal text-muted">{name.replace(/_/g, ' ')}</th>
                {completed.map((r) => {
                  const v = valueOf(r, name);
                  const best = bestOf(name);
                  const isBest = v !== null && best !== null && v === best;
                  return (
                    <td key={r.id} className={classNames('td tabular-nums', isBest && 'text-accent font-medium')}>
                      {v === null ? '—' : formatMetric(v)}
                      {isBest && <span className="ml-2 text-xs">best</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr>
              <th scope="row" className="td text-left font-normal text-muted align-top">Parameters</th>
              {completed.map((r) => (
                <td key={r.id} className="td align-top">
                  <pre className="whitespace-pre-wrap font-mono text-xs text-muted">{JSON.stringify(r.metrics.model_parameters || r.hyperparameters || {}, null, 1)}</pre>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  );
};

const RunEvents = ({ runId }) => {
  const { apiFetch } = useContext(AuthContext);
  const [events, setEvents] = useState([]);
  const [runStatus, setRunStatus] = useState(null);
  const afterRef = useRef(0);

  useEffect(() => {
    let active = true;
    let timer = null;
    const poll = () => {
      apiFetch(`/api/v1/ml/runs/${runId}/events?after=${afterRef.current}`)
        .then(data => {
          if (!active) return;
          setRunStatus(null);
          if (data.events && data.events.length) {
            afterRef.current = data.last_seq;
            setEvents(prev => [...prev, ...data.events].slice(-200));
          }
          // The stream keeps polling until the run is over; the run status
          // arrives from the parent, so the panel just watches the tail.
          timer = setTimeout(poll, 1500);
        })
        .catch(() => { if (active) timer = setTimeout(poll, 3000); });
    };
    poll();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [runId, apiFetch, runStatus]);

  if (!events.length) return null;

  // What an event says, in the words a person would use.
  const describe = (event) => {
    const payload = event.payload || {};
    if (event.kind === 'phase') {
      const { phase, ...detail } = payload;
      const extra = Object.entries(detail).map(([k, v]) => `${k.replace(/_/g, ' ')} ${isNumber(v) ? (Number.isInteger(v) ? v : fmtNum(v)) : v}`).join(', ');
      return { text: String(phase || ''), extra, tone: 'text-ink' };
    }
    if (event.kind === 'metric') {
      const pairs = Object.entries(payload).filter(([, v]) => v !== null && typeof v !== 'object');
      return { text: pairs.map(([k, v]) => `${k.replace(/_/g, ' ')} ${isNumber(v) ? (Number.isInteger(v) ? v : fmtNum(v)) : v}`).join(',  '), extra: '', tone: 'text-muted' };
    }
    return { text: payload.message || '', extra: '', tone: 'text-faint' };
  };

  return (
    <section className="panel" aria-label="Progress">
      <h2 className="mb-3">Progress</h2>
      <ol className="max-h-56 overflow-y-auto text-sm space-y-1 tabular-nums" aria-live="polite">
        {events.map((event) => {
          const line = describe(event);
          return (
            <li key={event.seq} className={line.tone}>
              {line.text}
              {line.extra && <span className="text-faint">{`  (${line.extra})`}</span>}
            </li>
          );
        })}
      </ol>
    </section>
  );
};

const RunDetails = ({ runId, navigate }) => {
  const { apiFetch } = useContext(AuthContext);
  const [run, setRun] = useState(null);
  const [model, setModel] = useState(null);
  const modelFetchedRef = useRef(null);
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [cancelNote, setCancelNote] = useState(null);
  // Bumped to read the run again at once (after a cancel).
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    let timer = null;
    setRun(null);
    setError(null);

    // The training runs in the background: the run is read again until it is
    // finished, so the metrics appear without a reload of the page. The next
    // read is scheduled when the previous one is done, so a slow answer cannot
    // pile up.
    const fetchRun = () => {
      apiFetch(`/api/v1/ml/runs/${runId}`)
        .then(data => {
          if (!active) return;
          setRun(data);
          // A run that is not completed, failed or cancelled is still going.
          const finished = ['completed', 'failed', 'cancelled'].includes(data.status);
          if (!finished) {
            timer = setTimeout(fetchRun, RUN_POLL_INTERVAL_MS);
          }
        })
        .catch(err => { if (active) setError(err); });
    };

    fetchRun();
    // The timer of a pending read is cleared, so no poll survives the view.
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [apiFetch, runId, reloadKey]);

  // The run only names its model: look up the catalog entry to know whether
  // the model is implemented. A placeholder model was never trained, so it
  // has no metrics - that is different from a run still waiting for metrics.
  // Fetched once per run; re-fetched when the run id changes.
  useEffect(() => {
    if (!run?.model_name) return;
    if (modelFetchedRef.current === runId) return;
    modelFetchedRef.current = runId;
    setModel(null);
    apiFetch(`/api/v1/ml/model-details?model_name=${encodeURIComponent(run.model_name)}`)
      .then(m => setModel(m))
      // The catalog lookup is secondary: if it fails the run still renders,
      // just without the "not implemented" banner.
      .catch(() => {});
  }, [runId, run?.model_name, apiFetch]);

  const handleCancel = async () => {
    setCancelling(true);
    setCancelNote(null);
    try {
      const answer = await apiFetch(`/api/v1/ml/runs/${runId}/cancel`, { method: 'POST' });
      // A running training cannot be interrupted: the answer says so.
      if (answer.note) setCancelNote(answer.note);
      setReloadKey((k) => k + 1);
    } catch (e) {
      setCancelNote(e.message || 'The run could not be cancelled.');
    } finally {
      setCancelling(false);
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const blob = await apiFetch(`/api/v1/ml/runs/${runId}/artifact`);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `model_run_${runId}.joblib`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      alert("Artifact not available or expired.");
    } finally {
      setDownloading(false);
    }
  };

  if (error) {
    return (
      <div className="space-y-6">
        <nav aria-label="Breadcrumb" className="text-sm text-muted">
          <a href="#/runs" className="hover:text-strong">Runs</a>
          <span className="mx-2 text-faint" aria-hidden="true">/</span>
          <span>#{runId}</span>
        </nav>
        <p role="alert" className="notice notice-bad">
          {error.status === 404
            ? `Run #${runId} does not exist, or it belongs to another account.`
            : `The run could not be loaded (${error.message}).`}
        </p>
      </div>
    );
  }

  if (!run) return <p className="text-muted">Loading the run...</p>;

  const effectiveParameters = run.metrics?.model_parameters;
  const live = run.status === 'queued' || run.status === 'running';
  const seconds = run.started_at && run.finished_at
    ? Math.max(0, Math.round((new Date(run.finished_at) - new Date(run.started_at)) / 1000))
    : null;
  const scalarMetrics = run.metrics
    ? Object.entries(run.metrics).filter(([k, v]) => !STRUCTURED_METRICS.has(k) && !k.startsWith('_') && (v === null || typeof v !== 'object'))
    : [];

  return (
    <div className="space-y-10">
      <nav aria-label="Breadcrumb" className="text-sm text-muted">
        <a href="#/runs" className="hover:text-strong">Runs</a>
        <span className="mx-2 text-faint" aria-hidden="true">/</span>
        <span>#{run.id}</span>
      </nav>

      <header className="flex flex-wrap items-start justify-between gap-4 -mt-5">
        <div>
          <h1 className="mb-1">{run.model_name}</h1>
          <p className="text-muted flex flex-wrap items-center gap-x-5 gap-y-1">
            <StatusMark status={run.status} />
            <span>{run.dataset_tag}</span>
            <span title={new Date(run.created_at).toLocaleString()}>Started {timeAgo(run.created_at)}</span>
            {seconds !== null && <span className="tabular-nums">Took {seconds} s</span>}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {live && (
            <button onClick={handleCancel} disabled={cancelling} className="btn btn-danger">
              {cancelling ? 'Cancelling...' : 'Cancel run'}
            </button>
          )}
          {run.status === 'completed' && run.artifact_path && (
            <button onClick={handleDownload} disabled={downloading} className="btn btn-quiet">
              {downloading ? 'Downloading...' : 'Download model'}
            </button>
          )}
        </div>
      </header>

      {cancelNote && <p role="status" className="notice">{cancelNote}</p>}

      {(live || run.status === 'failed') && <RunEvents runId={runId} />}

      {run.status === 'failed' && (
        <section className="panel">
          <h2 className="mb-2">This run failed</h2>
          <p className="notice notice-bad whitespace-pre-wrap break-words">{run.metrics?.error || 'The server did not say why.'}</p>
        </section>
      )}
      {run.status === 'cancelled' && (
        <section className="panel"><p className="text-muted">This run was cancelled, so it has no result.</p></section>
      )}
      {live && (
        <section className="panel">
          <p className="text-muted">
            {run.status === 'queued'
              ? 'Waiting for a free worker. This page updates by itself.'
              : 'Training. The result appears here when it finishes.'}
          </p>
        </section>
      )}
      {model && model.implemented === false && (
        <p className="notice notice-bad">This model is not implemented, so this run cannot have a result.</p>
      )}

      {run.status === 'completed' && run.metrics && (
        <>
          <EvaluationPanel metrics={run.metrics} />
          <ConfusionMatrix confusion={run.metrics.confusion_matrix} />
          <PreprocessingReport report={run.metrics.preprocessing} />
          {run.metrics.artifact_kind && <PredictPanel runId={runId} />}
        </>
      )}

      {run.status === 'completed' && scalarMetrics.length > 0 && (
        <section className="panel">
          <details>
            <summary className="cursor-pointer text-strong font-medium hover:text-accent">All metrics ({scalarMetrics.length})</summary>
            <dl className="mt-4 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-x-8 gap-y-3">
              {scalarMetrics.map(([key, val]) => (
                <div key={key} className="flex justify-between gap-4 border-b border-rule/60 pb-1">
                  <dt className="text-muted">{key.replace(/_/g, ' ')}</dt>
                  <dd className="text-strong tabular-nums text-right break-words">{formatMetric(val)}</dd>
                </div>
              ))}
            </dl>
          </details>
        </section>
      )}

      <section className="panel">
        <h2 className="mb-4">How it was trained</h2>
        <dl className="grid grid-cols-[10rem_1fr] gap-x-6 gap-y-3 max-w-prose">
          <dt className="text-muted">Data source</dt><dd className="capitalize">{run.dataset_source}</dd>
          <dt className="text-muted">Dataset</dt><dd className="break-all">{run.dataset_tag}</dd>
          {run.hf_dataset_url && (<><dt className="text-muted">Hugging Face</dt><dd><a href={run.hf_dataset_url} target="_blank" rel="noreferrer" className="link break-all">{run.hf_dataset_url}</a></dd></>)}
          {run.mode && (<><dt className="text-muted">Mode</dt><dd className="capitalize">{run.mode}</dd></>)}
          {run.env_id && (<><dt className="text-muted">Environment</dt><dd className="break-all">{run.env_id}</dd></>)}
        </dl>
        <details className="mt-6">
          <summary className="cursor-pointer text-strong font-medium hover:text-accent">Parameters</summary>
          <p className="text-sm text-muted mt-3 mb-2">What you submitted:</p>
          <pre className="field font-mono text-sm overflow-x-auto">{JSON.stringify(run.hyperparameters || {}, null, 2)}</pre>
          {effectiveParameters && Object.keys(effectiveParameters).length > 0 && (
            <>
              <p className="text-sm text-muted mt-4 mb-2">What was used (defaults, mode and preset merged):</p>
              <pre className="field font-mono text-sm overflow-x-auto">{JSON.stringify(effectiveParameters, null, 2)}</pre>
            </>
          )}
        </details>
      </section>
    </div>
  );
};

const NewJob = ({ navigate }) => {
  const { apiFetch } = useContext(AuthContext);
  const [models, setModels] = useState([]);
  const [modelsError, setModelsError] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [datasetsError, setDatasetsError] = useState(null);
  const [modelDetails, setModelDetails] = useState(null);
  const [modelDetailsError, setModelDetailsError] = useState(null);
  const [trainingModes, setTrainingModes] = useState(FALLBACK_TRAINING_MODES);
  const [modeDescriptions, setModeDescriptions] = useState(FALLBACK_MODE_DESCRIPTIONS);
  const [modesError, setModesError] = useState(null);
  const [trainingPresets, setTrainingPresets] = useState(FALLBACK_TRAINING_PRESETS);
  const [presetsError, setPresetsError] = useState(null);
  // Keys the user actually edited - an untouched blank field is omitted from the payload,
  // while a field the user cleared on purpose is sent as an explicit null.
  const [touchedParams, setTouchedParams] = useState({});
  
  const [sourceType, setSourceType] = useState('local');
  const [payload, setPayload] = useState({
    model_name: '',
    dataset_id: null,
    hf_dataset_url: '',
    label_column: 'label',
    test_size: 0.2,
    random_state: 42,
    // '' lets the server guess the task from the label column.
    task_type: '',
    cv_folds: 5,
    mode: 'manual',
    preset: 'balanced',
    env_id: '',
    hyperparameters: {}
  });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  // The state of the upload: the file is sent to the server, which registers
  // it as a dataset of the user.
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [uploadedDataset, setUploadedDataset] = useState(null);

  // The dataset that is selected in the form, and the columns it has: the
  // label column is picked from them, so it does not have to be typed.
  const selectedDataset = datasets.find(d => d.id === payload.dataset_id) || null;
  const labelColumnOptions = selectedDataset
    ? (selectedDataset.columns || []).map(column => column.name)
    : [];

  // The dataset is passed in when it is not in the list yet: after an upload
  // the list is updated in the same event handler, so the closure still holds
  // the old one and the lookup would find nothing.
  // The payload is updated with the functional form, so that a change the
  // user made while the upload was running is not rolled back.
  const selectDataset = (datasetId, knownDataset) => {
    const id = datasetId === '' || datasetId === null ? null : Number(datasetId);
    setPayload(previous => {
      const dataset = knownDataset || datasets.find(d => d.id === id);
      const columns = dataset ? (dataset.columns || []).map(column => column.name) : [];
      return {
        ...previous,
        dataset_id: id,
        // The registry suggests the label column; it is only used when the
        // suggestion is one of the columns of the file.
        label_column: dataset && dataset.label_column && columns.includes(dataset.label_column)
          ? dataset.label_column
          : (columns.includes(previous.label_column) ? previous.label_column : (columns[0] || previous.label_column)),
      };
    });
  };

  const handleUpload = async (event) => {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const dataset = await apiFetch('/api/v1/ml/datasets/upload', {
        method: 'POST',
        body: form,
      });
      setUploadedDataset(dataset);
      setDatasets(previous => {
        const without = previous.filter(item => item.id !== dataset.id);
        return [...without, dataset].sort((a, b) => a.name.localeCompare(b.name));
      });
      // The uploaded dataset is passed in: the list above is not updated yet.
      selectDataset(dataset.id, dataset);
    } catch (err) {
      setUploadError(err.message || 'The upload failed.');
    } finally {
      setUploading(false);
      // The input is cleared, so that the same file can be uploaded again.
      event.target.value = '';
    }
  };

  useEffect(() => {
    apiFetch('/api/v1/ml/models')
      .then(data => {
        setModels(Array.isArray(data) ? data : []);
        setModelsError(null);
      })
      // A failed request is not an empty model list: the built-in fallback list
      // keeps the form usable and the reason is reported below the select.
      .catch(err => {
        setModels(FALLBACK_MODELS);
        setModelsError(err.message || 'Unknown error');
      });
    apiFetch('/api/v1/ml/datasets')
      .then(data => { setDatasets(data?.datasets || []); setDatasetsError(null); })
      // A failed request is not the same as "the server has no datasets": the two
      // cases are reported separately so a backend outage is not mistaken for an
      // empty data directory.
      .catch(err => { setDatasets([]); setDatasetsError(err.message || 'Unknown error'); });
    apiFetch('/api/v1/ml/training-modes')
      .then(data => {
        if (Array.isArray(data?.modes) && data.modes.length > 0) setTrainingModes(data.modes);
        if (data?.descriptions && typeof data.descriptions === 'object') {
          setModeDescriptions({ ...FALLBACK_MODE_DESCRIPTIONS, ...data.descriptions });
        }
        setModesError(null);
      })
      // The form stays usable through the built-in fallback list, but the reason
      // is reported instead of being swallowed.
      .catch(err => { setModesError(err.message || 'Unknown error'); });
    apiFetch('/api/v1/ml/training-presets')
      .then(data => {
        setTrainingPresets(Array.isArray(data?.presets) ? data.presets : []);
        setPresetsError(null);
      })
      // The presets keep the form usable through the built-in fallback list and
      // the reason is reported below the preset buttons.
      .catch(err => {
        setTrainingPresets(FALLBACK_TRAINING_PRESETS);
        setPresetsError(err.message || 'Unknown error');
      });
  }, [apiFetch]);

  const selectedModelDef = models.find(m => m.name === payload.model_name);
  const isReinforcementLearning = selectedModelDef?.category === 'reinforcement-learning';
  const presetInfo = trainingPresets.find(p => p.name === payload.preset);
  // The mode description is the text the backend sends; the local copy is only
  // the fallback for an unreachable backend.
  const modeDescription = modeDescriptions[payload.mode]
    || FALLBACK_MODE_DESCRIPTIONS[payload.mode]
    || 'Parameters are configured automatically for this training mode.';
  const modeOptions = trainingModes.includes(payload.mode)
    ? trainingModes
    : [...trainingModes, payload.mode];
  // auto_search trains every candidate the client sends and keeps the best one, so
  // the client has to provide the candidate list. Only models of the same category
  // solve the same task and report comparable metrics, so the pool is the catalog
  // slice that shares the selected model's category. The estimator-backed
  // categories are the ones the backend can score against each other (the
  // transformer and vision models are not).
  const searchCandidates = selectedModelDef
    ? models
        .filter(m => m.category === selectedModelDef.category && COMPARABLE_MODEL_CATEGORIES.includes(m.category))
        .map(m => m.name)
    : [];

  // Fetch full model details when model changes
  useEffect(() => {
    if (payload.model_name) {
      // The previous model's details are dropped first: they must not be shown
      // next to the newly selected model while the request is in flight.
      setModelDetails(null);
      setModelDetailsError(null);
      apiFetch(`/api/v1/ml/model-details?model_name=${encodeURIComponent(payload.model_name)}`)
        .then(data => { setModelDetails(data); setModelDetailsError(null); })
        // A failed request is reported in place of the Model Intelligence panel
        // instead of leaving it silently missing.
        .catch(err => setModelDetailsError(err.message || 'Unknown error'));
    } else {
      setModelDetails(null);
      setModelDetailsError(null);
    }
  }, [payload.model_name, apiFetch]);

  // Auto-populate parameters when model changes
  useEffect(() => {
    if (!selectedModelDef) return;
    if (payload.mode === 'manual') {
      setPayload(prev => ({ ...prev, hyperparameters: { ...selectedModelDef.parameters } }));
      setTouchedParams({});
    } else {
      // The automatic modes let the backend pick the parameters. Sending the
      // catalog defaults would win the backend's merge (the request is applied
      // last), so the mode's own suggestion would never take effect.
      setPayload(prev => ({ ...prev, hyperparameters: {} }));
      setTouchedParams({});
    }
  }, [payload.model_name, payload.mode, selectedModelDef]);

  const handleParamChange = (key, value) => {
    setTouchedParams(prev => ({ ...prev, [key]: true }));
    setPayload(prev => ({
      ...prev,
      hyperparameters: { ...prev.hyperparameters, [key]: value }
    }));
  };

  // Builds the hyperparameters actually sent to the backend:
  // numeric catalog values stay numeric, blank untouched fields are omitted and a
  // field the user cleared is only sent as an explicit null when the estimator
  // accepts it (the catalog default is None).
  // An empty string is never sent for any type: the estimators reject it
  // (LogisticRegression(penalty="") -> 400, LinearRegression(fit_intercept="") ->
  // InvalidParameterError), so a cleared non-numeric field is dropped instead so
  // the catalog default applies.
  const buildHyperparameters = () => {
    const catalog = selectedModelDef?.parameters || {};
    const result = {};
    Object.entries(payload.hyperparameters).forEach(([key, val]) => {
      const definition = catalog[key];
      const isNumeric = typeof definition === 'number' || definition === null;
      const isBoolean = typeof definition === 'boolean';
      const raw = (val === null || val === undefined) ? '' : String(val).trim();
      if (raw === '') {
        // A cleared numeric field: an optional parameter (the catalog default is
        // None, e.g. max_depth) already accepts None there, so the cleared field is
        // sent as an explicit null. A parameter with a numeric default does not
        // accept None (LogisticRegression(C=None) is rejected), so its key is
        // dropped and the catalog default applies instead.
        if (isNumeric && touchedParams[key] && definition === null) result[key] = null;
        return;
      }
      if (isBoolean) {
        // A boolean parameter is edited in a text field, so the typed text is
        // converted back to a boolean - the estimator rejects the string "true".
        const lowered = raw.toLowerCase();
        if (lowered === 'true' || lowered === 'false') result[key] = lowered === 'true';
        return;
      }
      if (!isNumeric) {
        // A string parameter (an enum or a path): the trimmed text is sent.
        result[key] = raw;
        return;
      }
      const parsed = Number(raw);
      // A number input reports an empty string for invalid text, so a value that
      // is not a number is a safety net: the key is dropped and the catalog
      // default applies.
      if (Number.isFinite(parsed)) result[key] = parsed;
    });
    return result;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    // The backend rejects a run without a data source with a generic 400, so
    // the missing input is reported here instead of leaving the user with
    // that message.
    if (sourceType === 'local') {
      if (!isReinforcementLearning && !payload.dataset_id) {
        setError('Select a dataset before starting the run.');
        return;
      }
    } else if (!payload.hf_dataset_url) {
      setError('Enter a Hugging Face dataset URL or path before starting the run.');
      return;
    }

    setSubmitting(true);

    try {
      const submitPayload = { ...payload };
      if (sourceType === 'local') delete submitPayload.hf_dataset_url;
      if (sourceType === 'hf') delete submitPayload.dataset_id;
      submitPayload.hyperparameters = buildHyperparameters();
      // The metric the run is optimized for follows the task of the selected
      // model: a regression model is scored with r2, every other task with
      // accuracy. Without this every run would be recorded as an accuracy run,
      // which is wrong for a regression model.
      submitPayload.optimize_metric = selectedModelDef?.category === 'regression' ? 'r2' : 'accuracy';
      // Empty values are not valid for the backend: a null dataset id would be
      // stored as a "huggingface" run and an empty env id as "".
      if (!submitPayload.dataset_id) delete submitPayload.dataset_id;
      if (!submitPayload.hf_dataset_url) delete submitPayload.hf_dataset_url;
      if (!submitPayload.env_id) delete submitPayload.env_id;
      // auto_search needs the candidate list, otherwise the backend trains the
      // selected model alone and the mode does nothing.
      if (payload.mode === 'auto_search' && payload.model_name) {
        submitPayload.model_candidates = searchCandidates.length > 0
          ? searchCandidates
          : [payload.model_name];
      }

      // Ensure types are correct for numbers
      submitPayload.test_size = parseFloat(submitPayload.test_size);
      submitPayload.random_state = parseInt(submitPayload.random_state, 10);
      if (!submitPayload.task_type) delete submitPayload.task_type;
      submitPayload.cv_folds = parseInt(submitPayload.cv_folds, 10);
      
      // The training runs in the background: the answer carries the id of the
      // run and nothing else. The metrics are written in the run itself, so
      // the details view is the place to watch them.
      const result = await apiFetch('/api/v1/ml/train', {
        method: 'POST',
        body: JSON.stringify(submitPayload)
      });
      navigate('run-details', result.run_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const formatTestResults = () => {
    if (!modelDetails?.test_results) return null;
    const tr = modelDetails.test_results;
    
    return {
      accuracy: tr.expected_accuracy || tr.expected_r2 || tr.expected_reward || tr.expected_silhouette,
      accuracyLabel: tr.expected_accuracy ? 'Expected Accuracy' : 
                      tr.expected_r2 ? 'Expected R²' : 
                      tr.expected_reward ? 'Expected Reward' : 
                      'Expected Silhouette',
      bestFor: tr.best_for,
      trainingTime: tr.typical_training_time_sec,
      scalability: tr.scalability,
    };
  };

  const testResults = formatTestResults();

  return (
    <div className="max-w-6xl space-y-6">
      <div>
        <h1 className="mb-1">New run</h1>
        <p className="text-muted">Choose the data, the model, and how it should be trained.</p>
      </div>

      {error && (
        <div role="alert" className="notice notice-bad">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-8">
        
        {/* Section A: Data */}
        <div className="panel">
          <h2 className="mb-5">Data</h2>
          
          <div className="flex space-x-4 mb-6">
            <button
              type="button"
              onClick={() => setSourceType('local')}
              className={classNames("px-4 py-2 rounded-md text-sm font-medium transition-colors border", sourceType === 'local' ? "bg-raised border-rule text-strong" : "bg-transparent border-rule text-muted hover:text-strong")}
            >
              Local Dataset (CSV)
            </button>
            <button
              type="button"
              onClick={() => setSourceType('hf')}
              className={classNames("px-4 py-2 rounded-md text-sm font-medium transition-colors border", sourceType === 'hf' ? "bg-raised border-rule text-strong" : "bg-transparent border-rule text-muted hover:text-strong")}
            >
              Hugging Face Hub
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {sourceType === 'local' ? (
              <div>
                <label className="block text-sm text-muted mb-1.5">Select Local Dataset</label>
                {/* The select stays mounted when the list is empty so the "required"
                    rule keeps blocking the submission instead of posting an empty
                    dataset name to the backend. */}
                <select
                  required={!isReinforcementLearning}
                  value={payload.dataset_id ?? ''}
                  onChange={(e) => selectDataset(e.target.value)}
                  className="field"
                >
                  {datasets.length === 0 && (
                    <option value="" disabled>-- no datasets available --</option>
                  )}
                  {datasets.length > 0 && (
                    <option value="">-- Select --</option>
                  )}
                  {datasets.map(d => <option key={d.id} value={d.id}>{datasetOptionLabel(d)}</option>)}
                </select>
                {datasetsError && (
                  <p className="notice mt-2">
                    Could not load datasets: {datasetsError}
                  </p>
                )}
                {!datasetsError && datasets.length === 0 && (
                  <p className="text-sm text-faint mt-2">
                    No datasets available. Upload a CSV file below to start.
                  </p>
                )}
                {isReinforcementLearning && (
                  <p className="text-sm text-faint mt-1.5">Not required for reinforcement learning models.</p>
                )}
                {selectedDataset && selectedDataset.columns && selectedDataset.columns.length > 0 && (
                  <p className="text-sm text-faint mt-2">
                    {selectedDataset.row_count} rows, {selectedDataset.columns.length} columns
                    {selectedDataset.source === 'builtin' ? ', shipped with the repository' : ', uploaded by you'}
                  </p>
                )}
                {!isReinforcementLearning && (
                  <div className="mt-3">
                    <label className="block text-xs font-medium text-faint mb-1">Upload a CSV file</label>
                    <div className="flex items-center gap-3">
                      <input
                        type="file"
                        accept=".csv,text/csv"
                        onChange={handleUpload}
                        disabled={uploading}
                        className="text-sm text-muted file:mr-3 file:rounded-md file:border-0 file:bg-raised file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-ink hover:file:bg-rule disabled:opacity-50"
                      />
                      {uploading && <span role="status" className="text-sm text-muted">Uploading...</span>}
                    </div>
                    {uploadError && (
                      <p className="notice mt-2">
                        {uploadError}
                      </p>
                    )}
                    {uploadedDataset && (
                      <p className="notice mt-2">
                        Uploaded “{uploadedDataset.name}” with {uploadedDataset.row_count} rows. It is selected above.
                      </p>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="md:col-span-2">
                <label className="block text-sm text-muted mb-1.5">Hugging Face URL / Path</label>
                <input
                  type="text"
                  required
                  placeholder="e.g., databricks/databricks-dolly-15k"
                  value={payload.hf_dataset_url}
                  onChange={(e) => setPayload({...payload, hf_dataset_url: e.target.value})}
                  className="field"
                />
              </div>
            )}

            <div>
              <label className="block text-sm text-muted mb-1.5">Target / Label Column</label>
              {labelColumnOptions.length > 0 ? (
                <select
                  required
                  value={payload.label_column}
                  onChange={(e) => setPayload({...payload, label_column: e.target.value})}
                  className="field"
                >
                  {labelColumnOptions.map(name => <option key={name} value={name}>{name}</option>)}
                </select>
              ) : (
                <input
                  type="text"
                  required
                  placeholder="label"
                  value={payload.label_column}
                  onChange={(e) => setPayload({...payload, label_column: e.target.value})}
                  className="field"
                />
              )}
              {labelColumnOptions.length > 0 && (
                <p className="text-sm text-faint mt-1.5">The columns of the selected dataset.</p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
               <div>
                <label className="block text-sm text-muted mb-1.5">Test Size Split</label>
                <input 
                  type="number" 
                  step="0.01" min="0.01" max="0.99" required
                  value={payload.test_size}
                  onChange={(e) => setPayload({...payload, test_size: e.target.value})}
                  className="field"
                />
              </div>
               <div>
                <label className="block text-sm text-muted mb-1.5">Random State</label>
                <input 
                  type="number" 
                  required
                  value={payload.random_state}
                  onChange={(e) => setPayload({...payload, random_state: e.target.value})}
                  className="field"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-muted mb-1.5">Task type (tabular models)</label>
                <select
                  value={payload.task_type}
                  onChange={(e) => setPayload({...payload, task_type: e.target.value})}
                  className="field"
                >
                  <option value="">Guess from the label column</option>
                  <option value="classification">Classification</option>
                  <option value="regression">Regression</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-muted mb-1.5">Cross-validation folds (0 = off)</label>
                <input
                  type="number" min="0" max="20" required
                  value={payload.cv_folds}
                  onChange={(e) => setPayload({...payload, cv_folds: e.target.value})}
                  className="field"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Section B: Model & Mode Selection */}
        <div className="panel">
           <h2 className="mb-5">Architecture & Training Configuration</h2>
           
           <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
             <div>
                <label className="block text-sm text-muted mb-1.5">Model Selection</label>
                 <select 
                   required
                   value={payload.model_name}
                   onChange={(e) => setPayload({...payload, model_name: e.target.value})}
                   className="field"
                 >
                   <option value="">Choose a model</option>
                   {groupModels(models).map(([label, rows]) => (
                     <optgroup key={label} label={label}>
                       {rows.map((m) => {
                         const usable = m.implemented !== false && m.available !== false;
                         return (
                           <option key={m.name} value={m.name} disabled={!usable}>
                             {m.name}{usable ? '' : (m.implemented === false ? ' (not implemented)' : ' (not available here)')}
                           </option>
                         );
                       })}
                     </optgroup>
                   ))}
                 </select>
                 {modelsError && (
                   <p className="notice mt-2">
                     Could not load models — {modelsError}. Using the built-in fallback list.
                   </p>
                 )}
                 <p className="text-sm text-faint mt-1.5">
                   {(() => {
                     const chosen = models.find((m) => m.name === payload.model_name);
                     return chosen && chosen.description ? chosen.description : 'Greyed-out models cannot run on this server; the Models page says why.';
                   })()}
                 </p>
               </div>

             <div>
               <label className="block text-sm text-muted mb-1.5">Training Mode</label>
               <select
                 value={payload.mode}
                 onChange={(e) => setPayload({...payload, mode: e.target.value})}
                 className="field"
               >
                 {modeOptions.map(m => <option key={m} value={m}>{humanizeKey(m)}</option>)}
               </select>
               {modesError && (
                 <p className="text-xs text-warn/90 border border-warn/40 rounded-md px-3 py-2 mt-2">
                   Could not load the training modes — {modesError}. Using the built-in fallback list.
                 </p>
               )}
             </div>
           </div>

            {/* Mode Description */}
            {payload.mode !== 'manual' && (
              <div className="mb-6 p-3 bg-accent/15/20 border border-accent/50/50 rounded-md">
                <div className="text-sm text-accent">
                  <span className="font-semibold">Mode: {humanizeKey(payload.mode)}</span> - 
                  {modeDescription}
                </div>
              </div>
            )}

           {/* Preset Selector */}
           <div className="mb-6">
             <label className="block text-sm text-muted mb-1.5">Training Preset</label>
             <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
               {trainingPresets.map(p => (
                 <button
                   key={p.name}
                   type="button"
                   onClick={() => setPayload({...payload, preset: p.name})}
                   className={classNames(
                     "p-3 rounded-md border text-left transition-all",
                     payload.preset === p.name 
                       ? "bg-accent/15/40 border-accent/50 text-strong" 
                       : "bg-surface border-rule text-muted hover:border-faint/60"
                   )}
                 >
                    <div className="font-medium capitalize text-sm">{p.name}</div>
                    <div className="text-sm text-faint mt-1.5">{p.description}</div>
                  </button>
                ))}
              </div>
              {presetsError && (
                <p className="notice mt-2">
                  Could not load training presets — {presetsError}. Using the built-in fallback list.
                </p>
              )}
            </div>

           {selectedModelDef?.category === 'reinforcement-learning' && (
             <div className="mb-6">
                <label className="block text-sm text-muted mb-1.5">Gymnasium Environment ID (Required for RL)</label>
                <input 
                  type="text" 
                  required
                  placeholder="e.g., CartPole-v1"
                  value={payload.env_id}
                  onChange={(e) => setPayload({...payload, env_id: e.target.value})}
                  className="field"
                />
             </div>
           )}
        </div>

        {/* Section C: Model Details Panel */}
        {modelDetails && testResults && (
          <div className="bg-gradient-to-br from-blue-900/20 to-indigo-900/20 border border-accent/50/50 rounded-md p-6">
            <h3 className="text-lg font-semibold text-strong mb-4">📊 Model Intelligence</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-surface/50 rounded-md p-4 border border-rule/50">
                <div className="text-xs text-muted mb-2">{testResults.accuracyLabel}</div>
                <div className="text-lg font-bold text-accent">
                  {testResults.accuracy ? `${(testResults.accuracy[0]*100).toFixed(0)}% - ${(testResults.accuracy[1]*100).toFixed(0)}%` : 'N/A'}
                </div>
              </div>

              <div className="bg-surface/50 rounded-md p-4 border border-rule/50">
                <div className="text-xs text-muted mb-2">Training Time</div>
                <div className="text-lg font-bold text-ok">~{testResults.trainingTime}s</div>
              </div>

              <div className="bg-surface/50 rounded-md p-4 border border-rule/50">
                <div className="text-xs text-muted mb-2">Scalability</div>
                <div className={classNames("text-lg font-bold", 
                  testResults.scalability === 'high' ? 'text-ok' :
                  testResults.scalability === 'medium' ? 'text-warn' : 'text-orange-400'
                )}>
                  {testResults.scalability?.charAt(0).toUpperCase() + testResults.scalability?.slice(1)}
                </div>
              </div>

              <div className="bg-surface/50 rounded-md p-4 border border-rule/50">
                <div className="text-xs text-muted mb-2">Optimization Targets</div>
                <div className="text-sm text-ink">
                  {selectedModelDef?.optimization?.length > 0 ? selectedModelDef.optimization.slice(0, 2).join(', ') : 'N/A'}
                  {selectedModelDef?.optimization?.length > 2 && '...'}
                </div>
              </div>
            </div>

            {testResults.bestFor && (
              <div className="mt-4 pt-4 border-t border-rule/50">
                <div className="text-xs text-muted mb-2">Best For:</div>
                <div className="flex flex-wrap gap-2">
                  {testResults.bestFor.map((tag, idx) => (
                    <span key={idx} className="px-3 py-1 bg-accent/15/40 border border-accent/50/50 rounded-full text-xs text-accent">
                      {tag.replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* The Model Intelligence panel is replaced by the reason it could not be
            loaded, so the section never disappears without an explanation. */}
        {modelDetailsError && (
          <div className="notice text-sm">
            Could not load model details — {modelDetailsError}.
          </div>
        )}

        {/* Section D: Hyperparameters */}
        {selectedModelDef && payload.mode === 'manual' && (
          <div className="panel">
             <h2 className="mb-5">Hyperparameters</h2>
             
             {Object.keys(payload.hyperparameters).length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {Object.entries(payload.hyperparameters).map(([key, val]) => {
                  const definition = selectedModelDef?.parameters?.[key];
                  // A null catalog default is an optional numeric parameter (e.g. max_depth).
                  const isNumeric = typeof definition === 'number' || definition === null;
                  // The catalog cannot tell an integer default from a float one (JSON
                  // turns 1.0 into 1), so every numeric input accepts any value:
                  // step="1" would make C = 0.5 fail the browser's own validation.
                  const step = isNumeric ? 'any' : undefined;
                  return (
                   <div key={key}>
                    <label className="block text-xs tabular-nums text-faint mb-1">{key}</label>
                    <input
                       type={isNumeric ? 'number' : 'text'}
                       step={step}
                       value={val === null || val === undefined ? '' : val}
                       onChange={(e) => handleParamChange(key, e.target.value)}
                       className="field"
                    />
                   </div>
                  );
                })}
              </div>
             ) : (
              <div className="text-sm text-faint italic">No configurable parameters required or auto-adjusted mode selected.</div>
             )}
          </div>
        )}

        {selectedModelDef && payload.mode !== 'manual' && (
          <div className="panel">
             <h2 className="mb-5">Hyperparameters</h2>
             <div className="text-sm text-muted">
               <p className="mb-2">
                  In <span className="font-semibold">{humanizeKey(payload.mode)}</span> mode, hyperparameters will be automatically {
                    payload.mode === 'auto_tune' ? 'tuned via randomized search' :
                    payload.mode === 'auto_fine_tune' ? 'tuned around the current configuration' :
                    payload.mode === 'llm_fine_tune' ? 'suggested by Google Gemini' :
                    payload.mode === 'auto_search' ? 'model selection across candidates' : 'configured'
                  }.
               </p>
               {payload.mode === 'auto_search' && (
                 <p className="mb-2">
                   {searchCandidates.length > 0 ? (
                     <>
                       Compared models: <span className="tabular-nums text-ink">{searchCandidates.join(', ')}</span>
                     </>
                   ) : (
                     <>
                       No comparable candidate for {selectedModelDef.name} - it is trained on its own.
                     </>
                   )}
                 </p>
               )}
               <p>
                 {presetInfo && (
                   <>
                     <span className="font-semibold">Preset "{presetInfo.name}":</span> {presetInfo.description}
                   </>
                 )}
               </p>
             </div>
          </div>
        )}

        <div className="flex items-center justify-end gap-4 border-t border-rule pt-6">
          {!payload.model_name && <p className="text-sm text-faint">Choose a model to continue.</p>}
          <button type="submit" disabled={submitting || !payload.model_name} className="btn btn-primary">
            {submitting ? 'Queueing...' : 'Start run'}
          </button>
        </div>
      </form>
    </div>
  );
};



// --- the error boundary (plan H5) ------------------------------------------------
// One broken panel must not blank the whole page: the boundary catches what a
// render throws and keeps the navigation alive.

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error('The view failed to render:', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div role="alert" className="max-w-prose">
          <h2 className="mb-2">This view could not be shown</h2>
          <p className="notice notice-bad mb-5 break-words">
            {String((this.state.error && this.state.error.message) || this.state.error)}
          </p>
          <button
            onClick={() => { this.setState({ error: null }); this.props.onReset && this.props.onReset(); }}
            className="btn btn-quiet"
          >
            Back to the runs
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// --- MAIN APP COMPONENT ---

const MainApp = () => {
  const { user, logout, apiFetch } = useContext(AuthContext);
  const [currentView, setCurrentView] = useState('runs');
  const [activeParams, setActiveParams] = useState(null);
  // The authoritative role and the usage of the caller (plan A7): a quota
  // the user cannot see is experienced as a bug, and the admin section is
  // visible only to an admin.
  const [me, setMe] = useState(null);

  useEffect(() => {
    apiFetch('/api/v1/me').then(setMe).catch(() => {});
  }, [apiFetch]);

  // The addressable pages of plan E4: the hash carries the view and its
  // parameter, so a run page and a comparison survive a reload and can be
  // sent as a link (#/run-details/3, #/compare/3+5+8).
  const navigate = useCallback((view, params = null) => {
    const hash = params === null || params === undefined || params === ''
      ? `#/${view}`
      : `#/${view}/${encodeURIComponent(Array.isArray(params) ? params.join('+') : params)}`;
    if (window.location.hash !== hash) {
      window.location.hash = hash;
    }
    setCurrentView(view);
    setActiveParams(params);
  }, []);

  useEffect(() => {
    const readHash = () => {
      const raw = window.location.hash.replace(/^#\//, '');
      if (!raw) return;
      const [view, encoded] = raw.split('/');
      let params = null;
      if (encoded) {
        const decoded = decodeURIComponent(encoded);
        params = decoded.includes('+') ? decoded.split('+').map(Number).filter(n => !isNaN(n)) : decoded;
        if (view === 'run-details') params = decoded;
      }
      setCurrentView(view || 'runs');
      setActiveParams(params);
    };
    readHash();
    window.addEventListener('hashchange', readHash);
    return () => window.removeEventListener('hashchange', readHash);
  }, []);

  const renderView = () => {
    switch (currentView) {
      case 'models': return <ModelsCatalog />;
      case 'runs': return <RunsDashboard navigate={navigate} />;
      case 'run-details': return <RunDetails runId={activeParams} navigate={navigate} />;
      case 'compare': return <CompareRuns runIds={activeParams} navigate={navigate} />;
      case 'new-job': return <NewJob navigate={navigate} />;
      case 'admin': return <AdminScreen apiFetch={apiFetch} />;
      default: return <RunsDashboard navigate={navigate} />;
    }
  };

  const formatBytes = (n) => (n >= 1024 * 1024 ? `${(n / (1024 * 1024)).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`);
  const usage = me?.usage;
  const inRuns = ['runs', 'run-details', 'compare'].includes(currentView);
  const nav = [
    { id: 'runs', label: 'Runs', active: inRuns },
    { id: 'models', label: 'Models', active: currentView === 'models' },
    { id: 'new-job', label: 'New run', active: currentView === 'new-job' },
    ...(me?.role === 'admin' ? [{ id: 'admin', label: 'Admin', active: currentView === 'admin' }] : []),
  ];

  return (
    <div className="min-h-screen">
      <header className="border-b border-rule">
        <div className="max-w-page mx-auto px-5 md:px-8 flex flex-wrap items-center gap-x-8 gap-y-2 py-3">
          <span className="font-semibold text-strong">PrimeTrade AutoML</span>
          <nav aria-label="Main" className="flex items-center gap-1 -mx-2">
            {nav.map((item) => (
              <a
                key={item.id}
                href={`#/${item.id}`}
                aria-current={item.active ? 'page' : undefined}
                className={classNames(
                  'px-2 py-1 text-sm rounded transition-colors border-b-2 whitespace-nowrap',
                  item.active ? 'text-strong border-accent' : 'text-muted border-transparent hover:text-strong'
                )}
              >
                {item.label}
              </a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-4 text-sm text-muted">
            {usage && (
              <span className="hidden sm:inline tabular-nums">
                {usage.limits?.max_runs_per_day
                  ? `${usage.runs_today} of ${usage.limits.max_runs_per_day} runs today`
                  : `${usage.runs_today} runs today`}
                {`, ${formatBytes(usage.storage_bytes)} stored`}
              </span>
            )}
            <span className="text-strong">{user?.sub}</span>
            <button onClick={logout} className="hover:text-strong underline-offset-4 hover:underline">Sign out</button>
          </div>
        </div>
      </header>
      <main className="max-w-page mx-auto px-5 md:px-8 py-8 md:py-10">
        {/* One broken view must not blank the page: the navigation stays alive. */}
        <ErrorBoundary key={`${currentView}:${String(activeParams)}`} onReset={() => navigate('runs')}>
          {renderView()}
        </ErrorBoundary>
      </main>
    </div>
  );
};


// --- ENTRY POINT ---

export default function App() {
  const [authMode, setAuthMode] = useState('login');

  return (
    <AuthProvider>
      <AuthContext.Consumer>
        {({ token }) => (
          token ? <MainApp /> : <AuthView mode={authMode} setMode={setAuthMode} />
        )}
      </AuthContext.Consumer>
    </AuthProvider>
  );
}