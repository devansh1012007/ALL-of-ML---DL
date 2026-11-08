// Moved verbatim from App.jsx in R6 (Frontend UI redesign); only import/export wiring changed.
import React, { useState, useCallback, createContext } from 'react';

// --- CONFIGURATION ---
export const API_BASE = 'http://localhost:8010';
// How often a run that is still going is read again. The training runs in the
// background, so the metrics of a run appear when a poll sees them.
export const RUN_POLL_INTERVAL_MS = 2000;

// --- UTILITIES ---
// JWT segments are base64url encoded ("-" / "_" instead of "+" / "/"), so they must be
// translated and padded before atob() can decode them.
export const parseJwt = (token) => {
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
export const formatApiDetail = (detail, status) => {
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

export const humanizeKey = (value) =>
  String(value)
    .replace(/_/g, ' ')
    .replace(/\bllm\b/gi, 'LLM')
    .replace(/\b\w/g, char => char.toUpperCase());

export const STATUS_LABELS = { queued: 'Queued', running: 'Running', completed: 'Completed', failed: 'Failed', cancelled: 'Cancelled' };
export const STATUS_TONES = { completed: 'bg-ok', failed: 'bg-bad', running: 'bg-accent animate-pulse', queued: 'bg-faint', cancelled: 'bg-faint' };

// A status is a dot and a word: the word carries the meaning, the dot only helps scanning.
export const StatusMark = ({ status }) => (
  <span className="inline-flex items-center gap-2">
    <span className={classNames('dot', STATUS_TONES[status])} aria-hidden="true" />
    <span>{STATUS_LABELS[status] || status}</span>
  </span>
);

export const classNames = (...classes) => classes.filter(Boolean).join(' ');

// Shell breadcrumb (R2): one trail for every nested view, aria-current on the
// current page, and the same hash destinations the hand-rolled trails used.
// Items ending in a plain span are the current page; items with href are links.
export const Breadcrumb = ({ items }) => (
  <nav aria-label="Breadcrumb" className="breadcrumb">
    <ol>
      {items.map((item, i) => {
        const isCurrent = i === items.length - 1;
        return (
          <li key={`${item.label}-${i}`}>
            {item.href && !isCurrent
              ? <a href={item.href}>{item.label}</a>
              : <span {...(isCurrent ? { 'aria-current': 'page' } : {})}>{item.label}</span>}
            {!isCurrent && <span className="text-faint" aria-hidden="true">/</span>}
          </li>
        );
      })}
    </ol>
  </nav>
);

// Fallbacks used when the training-modes endpoint cannot be reached.
export const FALLBACK_TRAINING_MODES = ['manual', 'auto_tune', 'auto_fine_tune', 'llm_fine_tune', 'auto_search'];
export const FALLBACK_MODE_DESCRIPTIONS = {
  manual: 'User-defined hyperparameters - full control over training settings',
  auto_tune: 'Randomized hyperparameter search over a curated per-model space',
  auto_fine_tune: 'Local hyperparameter search around the current configuration',
  llm_fine_tune: 'AI-guided parameters via Google Gemini (requires GOOGLE_API_KEY and the google-generativeai package)',
  auto_search: 'Model selection over multiple candidates - not Bayesian optimization',
};

// Fallback used when the training-presets endpoint cannot be reached.
export const FALLBACK_TRAINING_PRESETS = [
  { name: 'conservative', description: 'Low learning rate, high regularization, fewer iterations' },
  { name: 'balanced', description: 'Default settings optimized for most use cases' },
  { name: 'aggressive', description: 'High learning rate, low regularization, more iterations' },
];

// Fallback used when the model catalog cannot be reached. Only the core
// estimator-backed models are listed, with the categories the form needs (a
// regression model has to be recognisable as one). The names match the backend
// catalog, so a run submitted from the fallback still trains on the server.
export const FALLBACK_MODELS = [
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
export const COMPARABLE_MODEL_CATEGORIES = ['classification', 'regression', 'time-series'];

// The label of a dataset in the select of the new-job form: the name, and a
// hint of where it comes from, so that the datasets of the repository and the
// uploaded ones can be told apart.
export const datasetOptionLabel = (dataset) => {
  if (!dataset) return '';
  const parts = [dataset.name];
  if (dataset.source === 'builtin') parts.push('(built-in)');
  else if (dataset.source === 'upload') parts.push('(yours)');
  else parts.push('(folder)');
  return parts.join(' ');
};

// --- AUTH CONTEXT ---
export const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
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
    }).catch(() => {
      // A network failure (offline, DNS, refused) has no HTTP status and no
      // server `detail`: show one friendly sentence instead of the browser's
      // raw `TypeError: Failed to fetch` at every caller.
      throw new Error('Could not reach the server. Check your connection and try again.');
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
      const detail = errData && errData.detail;
      // DECISION: a non-JSON error body (HTML/plaintext error page, no usable
      // `detail`) has nothing server-authored to show verbatim. Fall back to
      // the connectivity sentence instead of the raw "HTTP error! status: …",
      // while a real JSON `detail` is still shown verbatim below.
      const hasDetail =
        (typeof detail === 'string' && detail.trim()) ||
        (Array.isArray(detail) && detail.length > 0) ||
        (detail && typeof detail === 'object');
      const error = new Error(
        hasDetail
          ? formatApiDetail(detail, response.status)
          : 'Could not reach the server. Check your connection and try again.'
      );
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

// The order and the names in which the catalog is shown.
export const MODEL_GROUPS = [
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
export const DATASET_KIND_LABELS = {
  tabular: 'A table (CSV)',
  timeseries: 'A time series (CSV)',
  graph: 'A graph (nodes and edges)',
  text: 'Text',
  text_pairs: 'Pairs of texts',
  image_folder: 'A folder of images, one subfolder per class',
};

// The models in the order and under the names of the catalog page.
export const groupModels = (models) => {
  const known = new Set(MODEL_GROUPS.map(([c]) => c));
  const groups = MODEL_GROUPS
    .map(([category, label]) => [label, models.filter((m) => m.category === category)])
    .filter(([, rows]) => rows.length > 0);
  const other = models.filter((m) => !known.has(m.category));
  if (other.length > 0) groups.push(['Other', other]);
  return groups;
};
