import React, { useState, useEffect, createContext, useContext, useCallback } from 'react';
import { 
  Activity, Database, Server, PlusCircle, LogOut, ChevronRight, 
  Play, CheckCircle, XCircle, Clock, Download, Lock, User
} from 'lucide-react';

// --- CONFIGURATION ---
const API_BASE = 'http://localhost:8010';

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
    if (typeof detail.message === 'string') return detail.message;
    return JSON.stringify(detail);
  }
  return `HTTP error! status: ${status}`;
};

const humanizeKey = (value) =>
  String(value)
    .replace(/_/g, ' ')
    .replace(/\bllm\b/gi, 'LLM')
    .replace(/\b\w/g, char => char.toUpperCase());

const classNames = (...classes) => classes.filter(Boolean).join(' ');

// Fallbacks used when the training-modes endpoint cannot be reached.
const FALLBACK_TRAINING_MODES = ['manual', 'auto_tune', 'auto_fine_tune', 'llm_fine_tune', 'auto_search'];
const FALLBACK_MODE_DESCRIPTIONS = {
  manual: 'User-defined hyperparameters - full control over training settings',
  auto_tune: 'Grid search optimization - automatically searches for optimal parameters',
  auto_fine_tune: 'Adaptive tuning - fine-tuning with reduced learning rates for stability',
  llm_fine_tune: 'AI-guided parameters - uses Google Gemini to suggest optimal hyperparameters',
  auto_search: 'Bayesian optimization - searches across multiple model candidates',
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

const SidebarItem = ({ icon: Icon, label, active, onClick }) => (
  <button
    onClick={onClick}
    className={classNames(
      "w-full flex items-center space-x-3 px-4 py-3 rounded-md text-sm font-medium transition-colors",
      active ? "bg-zinc-800 text-white" : "text-zinc-400 hover:bg-zinc-800/50 hover:text-white"
    )}
  >
    <Icon className="w-5 h-5" />
    <span>{label}</span>
  </button>
);

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

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-zinc-100">
      <div className="w-full max-w-md p-8 bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl">
        <div className="flex justify-center mb-8">
          <div className="w-12 h-12 bg-blue-600 rounded-lg flex items-center justify-center">
            <Activity className="w-6 h-6 text-white" />
          </div>
        </div>
        <h2 className="text-2xl font-bold text-center mb-6">
          {mode === 'login' ? 'Sign In to PrimeTrade' : 'Create an Account'}
        </h2>
        {sessionNotice && (
          <div className="mb-4 p-3 bg-amber-900/40 border border-amber-500 rounded text-amber-200 text-sm">
            {sessionNotice}
          </div>
        )}
        {error && (
          <div className="mb-4 p-3 bg-red-900/50 border border-red-500 rounded text-red-200 text-sm">
            {error}
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-1">Username</label>
            <div className="relative">
              <User className="absolute left-3 top-2.5 w-5 h-5 text-zinc-500" />
              <input
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full pl-10 pr-4 py-2 bg-zinc-950 border border-zinc-800 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-white"
                placeholder="admin"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-1">Password</label>
            <div className="relative">
              <Lock className="absolute left-3 top-2.5 w-5 h-5 text-zinc-500" />
              <input
                type="password"
                required
                minLength={mode === 'register' ? 8 : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-10 pr-4 py-2 bg-zinc-950 border border-zinc-800 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-white"
                placeholder="••••••••"
              />
            </div>
            {mode === 'register' && (
              <p className="mt-1 text-xs text-zinc-500">At least 8 characters.</p>
            )}
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md font-medium transition-colors disabled:opacity-50"
          >
            {loading ? 'Processing...' : (mode === 'login' ? 'Sign In' : 'Register')}
          </button>
        </form>
        <div className="mt-6 text-center text-sm text-zinc-500">
          {mode === 'login' ? (
            <p>Don't have an account? <button onClick={() => setMode('register')} className="text-blue-500 hover:underline">Register</button></p>
          ) : (
            <p>Already have an account? <button onClick={() => setMode('login')} className="text-blue-500 hover:underline">Sign In</button></p>
          )}
        </div>
      </div>
    </div>
  );
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

  const getAccuracyRange = (testResults) => {
    if (!testResults) return null;
    if (testResults.expected_accuracy) return `${(testResults.expected_accuracy[0]*100).toFixed(0)}-${(testResults.expected_accuracy[1]*100).toFixed(0)}%`;
    if (testResults.expected_r2) return `R²: ${(testResults.expected_r2[0]*100).toFixed(0)}-${(testResults.expected_r2[1]*100).toFixed(0)}%`;
    if (testResults.expected_silhouette) return `Silhouette: ${testResults.expected_silhouette[0].toFixed(2)}-${testResults.expected_silhouette[1].toFixed(2)}`;
    return null;
  };

  const getScalabilityColor = (scalability) => {
    switch(scalability) {
      case 'high': return 'bg-emerald-900/20 text-emerald-400 border-emerald-700/50';
      case 'medium': return 'bg-yellow-900/20 text-yellow-400 border-yellow-700/50';
      case 'low': return 'bg-orange-900/20 text-orange-400 border-orange-700/50';
      default: return 'bg-zinc-800 text-zinc-400';
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">Model Catalog</h1>
        <p className="text-zinc-400">Available architectures with performance estimates and recommended use cases.</p>
      </div>
      {modelsError && (
        <p className="text-sm text-amber-200/90 border border-amber-700/50 rounded-md px-3 py-2">
          Could not load the model catalog — {modelsError}. Showing the built-in fallback list.
        </p>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {models.map(model => (
          <div key={model.name} className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 flex flex-col hover:border-blue-700/50 transition-colors">
            <div className="flex justify-between items-start mb-2">
              <h3 className="text-lg font-semibold text-white">{model.name}</h3>
              <span className="px-2 py-1 bg-zinc-800 text-zinc-300 text-xs rounded-full uppercase tracking-wider">
                {model.category}
              </span>
            </div>
            <p className="text-sm text-zinc-400 mb-4 flex-grow">{model.description}</p>
            
            {/* Test Results Summary */}
            {model.test_results && (
              <div className="mb-4 p-3 bg-zinc-950/50 rounded border border-zinc-800/50 space-y-2">
                {getAccuracyRange(model.test_results) && (
                  <div className="text-xs">
                    <span className="text-zinc-400">Est. Performance:</span>
                    <span className="text-blue-400 ml-2 font-semibold">{getAccuracyRange(model.test_results)}</span>
                  </div>
                )}
                <div className="text-xs">
                  <span className="text-zinc-400">Training Time:</span>
                  <span className="text-zinc-300 ml-2 font-mono">~{model.test_results.typical_training_time_sec}s</span>
                </div>
                <div className="text-xs flex items-center gap-2">
                  <span className="text-zinc-400">Scalability:</span>
                  <span className={classNames("px-2 py-0.5 rounded text-xs font-semibold border", getScalabilityColor(model.test_results.scalability))}>
                    {model.test_results.scalability?.charAt(0).toUpperCase() + model.test_results.scalability?.slice(1)}
                  </span>
                </div>
                {model.test_results.best_for && model.test_results.best_for.length > 0 && (
                  <div className="text-xs pt-2 border-t border-zinc-700/50">
                    <span className="text-zinc-400 block mb-1">Best for:</span>
                    <div className="flex flex-wrap gap-1">
                      {model.test_results.best_for.slice(0, 2).map((use, idx) => (
                        <span key={idx} className="bg-blue-900/30 text-blue-300 px-1.5 py-0.5 rounded text-xs">
                          {use.replace(/_/g, ' ').substring(0, 15)}...
                        </span>
                      ))}
                      {model.test_results.best_for.length > 2 && (
                        <span className="text-zinc-500 text-xs">+{model.test_results.best_for.length - 2} more</span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Parameters */}
            <div className="bg-zinc-950 rounded p-3 text-xs font-mono text-zinc-500 border border-zinc-800/50">
              {Object.keys(model.parameters).length > 0 ? (
                <div className="space-y-1">
                  {Object.entries(model.parameters).slice(0, 3).map(([k, v]) => (
                    <div key={k}><span className="text-zinc-400">{k}:</span> {JSON.stringify(v)}</div>
                  ))}
                  {Object.keys(model.parameters).length > 3 && (
                    <div className="text-zinc-600">+{Object.keys(model.parameters).length - 3} more parameters</div>
                  )}
                </div>
              ) : "No configurable parameters."}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const RunsDashboard = ({ navigate }) => {
  const { apiFetch } = useContext(AuthContext);
  const [runs, setRuns] = useState([]);
  const [runsError, setRunsError] = useState(null);

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

  const getStatusIcon = (status) => {
    switch(status) {
      case 'completed': return <CheckCircle className="w-4 h-4 text-emerald-500" />;
      case 'failed': return <XCircle className="w-4 h-4 text-red-500" />;
      case 'running': return <Activity className="w-4 h-4 text-blue-500 animate-pulse" />;
      default: return <Clock className="w-4 h-4 text-zinc-500" />;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white mb-2">Training Runs</h1>
          <p className="text-zinc-400">Monitor and inspect ML pipeline executions.</p>
        </div>
        <button 
          onClick={() => navigate('new-job')}
          className="flex items-center space-x-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md font-medium"
        >
          <PlusCircle className="w-4 h-4" />
          <span>New Training Job</span>
        </button>
      </div>

      {runsError && (
        <p className="text-sm text-amber-200/90 border border-amber-700/50 rounded-md px-3 py-2">
          Could not load the training runs — {runsError}.
        </p>
      )}

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-950 text-zinc-400 border-b border-zinc-800 uppercase tracking-wider">
            <tr>
              <th className="px-6 py-4 font-medium">ID</th>
              <th className="px-6 py-4 font-medium">Model</th>
              <th className="px-6 py-4 font-medium">Dataset</th>
              <th className="px-6 py-4 font-medium">Status</th>
              <th className="px-6 py-4 font-medium">Primary Metric</th>
              <th className="px-6 py-4 font-medium">Started</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {runs.length === 0 && !runsError && (
              <tr>
                <td colSpan="6" className="px-6 py-8 text-center text-zinc-500">No training runs found.</td>
              </tr>
            )}
            {runs.map(run => (
              <tr 
                key={run.id} 
                onClick={() => navigate('run-details', run.id)}
                className="hover:bg-zinc-800/50 cursor-pointer transition-colors text-zinc-300"
              >
                <td className="px-6 py-4 font-mono text-zinc-500">#{run.id}</td>
                <td className="px-6 py-4 font-medium text-white">{run.model_name}</td>
                <td className="px-6 py-4 truncate max-w-[200px]">{run.dataset_tag}</td>
                <td className="px-6 py-4">
                  <div className="flex items-center space-x-2">
                    {getStatusIcon(run.status)}
                    <span className="capitalize">{run.status}</span>
                  </div>
                </td>
                <td className="px-6 py-4 font-mono">
                  {run.metrics?.accuracy ? `Acc: ${run.metrics.accuracy.toFixed(4)}` : 
                   run.metrics?.mse ? `MSE: ${run.metrics.mse.toFixed(4)}` : '-'}
                </td>
                <td className="px-6 py-4 text-zinc-500">
                  {new Date(run.created_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const RunDetails = ({ runId, navigate }) => {
  const { apiFetch } = useContext(AuthContext);
  const [run, setRun] = useState(null);
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    let active = true;
    setRun(null);
    setError(null);
    apiFetch(`/api/v1/ml/runs/${runId}`)
      .then(data => { if (active) setRun(data); })
      .catch(err => { if (active) setError(err); });
    return () => { active = false; };
  }, [apiFetch, runId]);

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
        <div className="flex items-center space-x-2 text-sm text-zinc-500">
          <button onClick={() => navigate('runs')} className="hover:text-white">Runs</button>
          <ChevronRight className="w-4 h-4" />
          <span className="text-zinc-300">Run #{runId}</span>
        </div>
        <div className="bg-red-900/30 border border-red-500/50 p-4 rounded-md text-red-200">
          {error.status === 404
            ? `Run #${runId} was not found.`
            : `Failed to load run details: ${error.message}`}
        </div>
      </div>
    );
  }

  if (!run) return <div className="text-zinc-500 p-8">Loading details...</div>;

  const effectiveParameters = run.metrics?.model_parameters;

  return (
    <div className="space-y-6">
      <div className="flex items-center space-x-2 text-sm text-zinc-500 mb-6">
        <button onClick={() => navigate('runs')} className="hover:text-white">Runs</button>
        <ChevronRight className="w-4 h-4" />
        <span className="text-zinc-300">Run #{run.id}</span>
      </div>

      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">{run.model_name}</h1>
          <div className="flex items-center space-x-4 text-sm text-zinc-400">
            <span className="bg-zinc-800 px-2 py-1 rounded text-zinc-300 uppercase tracking-wide">
              {run.status}
            </span>
            <span>Started: {new Date(run.created_at).toLocaleString()}</span>
          </div>
        </div>
        {run.status === 'completed' && run.artifact_path && (
          <button 
            onClick={handleDownload}
            disabled={downloading}
            className="flex items-center space-x-2 bg-zinc-100 hover:bg-white text-zinc-900 px-4 py-2 rounded-md font-medium disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            <span>{downloading ? 'Downloading...' : 'Download Artifact'}</span>
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Execution Metrics</h3>
            {run.status === 'failed' ? (
              <div className="bg-red-950/30 border border-red-900 rounded p-4 text-red-400 font-mono text-sm whitespace-pre-wrap">
                {run.metrics?.error || "Unknown execution error."}
              </div>
            ) : run.metrics ? (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {Object.entries(run.metrics).filter(([k]) => k !== 'model_parameters').map(([key, val]) => (
                  <div key={key} className="bg-zinc-950 p-4 rounded-md border border-zinc-800/50">
                    <div className="text-xs text-zinc-500 uppercase tracking-wider mb-1">{key.replace(/_/g, ' ')}</div>
                    <div className="text-xl font-mono text-zinc-200">
                      {val === null || val === undefined
                        ? '—'
                        : (typeof val === 'number' ? (Number.isInteger(val) ? val : val.toFixed(4)) : String(val))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-zinc-500">No metrics available yet.</p>
            )}
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Submitted hyperparameters</h3>
            <pre className="bg-zinc-950 p-4 rounded-md text-sm text-zinc-400 font-mono overflow-x-auto border border-zinc-800/50">
              {JSON.stringify(run.hyperparameters || {}, null, 2)}
            </pre>
            {effectiveParameters && Object.keys(effectiveParameters).length > 0 && (
              <>
                <h4 className="text-sm font-semibold text-zinc-300 mt-5 mb-2">Effective parameters</h4>
                <p className="text-xs text-zinc-500 mb-2">
                  Parameters actually used for training (catalog defaults merged with mode / preset adjustments).
                </p>
                <pre className="bg-zinc-950 p-4 rounded-md text-sm text-zinc-400 font-mono overflow-x-auto border border-zinc-800/50">
                  {JSON.stringify(effectiveParameters, null, 2)}
                </pre>
              </>
            )}
          </div>
        </div>

        <div className="space-y-6">
           <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Data Provenance</h3>
            <div className="space-y-4">
              <div>
                <label className="text-xs text-zinc-500 uppercase tracking-wider block mb-1">Source Type</label>
                <div className="text-zinc-300 capitalize">{run.dataset_source}</div>
              </div>
              <div>
                <label className="text-xs text-zinc-500 uppercase tracking-wider block mb-1">Identifier / Tag</label>
                <div className="text-zinc-300 break-all">{run.dataset_tag}</div>
              </div>
              {run.hf_dataset_url && (
                <div>
                  <label className="text-xs text-zinc-500 uppercase tracking-wider block mb-1">Hugging Face URL</label>
                  <a href={run.hf_dataset_url} target="_blank" rel="noreferrer" className="text-blue-400 hover:underline break-all">
                    {run.hf_dataset_url}
                  </a>
                </div>
              )}
              {run.mode && (
                <div>
                  <label className="text-xs text-zinc-500 uppercase tracking-wider block mb-1">Training Mode</label>
                  <div className="text-zinc-300 capitalize">{run.mode}</div>
                </div>
              )}
              {run.env_id && (
                <div>
                  <label className="text-xs text-zinc-500 uppercase tracking-wider block mb-1">Environment ID</label>
                  <div className="text-zinc-300 break-all">{run.env_id}</div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
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
    dataset_name: '',
    hf_dataset_url: '',
    label_column: 'label',
    test_size: 0.2,
    random_state: 42,
    mode: 'manual',
    preset: 'balanced',
    env_id: '',
    hyperparameters: {}
  });
  
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

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

    // The backend rejects a run without a data source with a generic 400
    // ("Either dataset_name or hf_dataset_url must be provided"), so the missing
    // input is reported here instead of leaving the user with that message.
    if (sourceType === 'local') {
      if (!isReinforcementLearning && !payload.dataset_name) {
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
      if (sourceType === 'hf') delete submitPayload.dataset_name;
      submitPayload.hyperparameters = buildHyperparameters();
      // The metric the run is optimized for follows the task of the selected
      // model: a regression model is scored with r2, every other task with
      // accuracy. Without this every run would be recorded as an accuracy run,
      // which is wrong for a regression model.
      submitPayload.optimize_metric = selectedModelDef?.category === 'regression' ? 'r2' : 'accuracy';
      // Empty strings are not valid values for the backend: an empty dataset name
      // would be stored as a "huggingface" run and an empty env id as "".
      if (!submitPayload.dataset_name) delete submitPayload.dataset_name;
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
        <h1 className="text-2xl font-bold text-white mb-2">Configure Training Job</h1>
        <p className="text-zinc-400">Specify data sources, model architectures, and training constraints.</p>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-500/50 p-4 rounded-md text-red-200">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-8">
        
        {/* Section A: Data */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-white mb-4 border-b border-zinc-800 pb-2">1. Data Ingestion</h2>
          
          <div className="flex space-x-4 mb-6">
            <button
              type="button"
              onClick={() => setSourceType('local')}
              className={classNames("px-4 py-2 rounded-md text-sm font-medium transition-colors border", sourceType === 'local' ? "bg-zinc-800 border-zinc-700 text-white" : "bg-transparent border-zinc-800 text-zinc-400 hover:text-white")}
            >
              Local Dataset (CSV)
            </button>
            <button
              type="button"
              onClick={() => setSourceType('hf')}
              className={classNames("px-4 py-2 rounded-md text-sm font-medium transition-colors border", sourceType === 'hf' ? "bg-zinc-800 border-zinc-700 text-white" : "bg-transparent border-zinc-800 text-zinc-400 hover:text-white")}
            >
              Hugging Face Hub
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {sourceType === 'local' ? (
              <div>
                <label className="block text-sm font-medium text-zinc-400 mb-1">Select Local Dataset</label>
                {/* The select stays mounted when the list is empty so the "required"
                    rule keeps blocking the submission instead of posting an empty
                    dataset name to the backend. */}
                <select
                  required={!isReinforcementLearning}
                  value={payload.dataset_name}
                  onChange={(e) => setPayload({...payload, dataset_name: e.target.value})}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-blue-500"
                >
                  {datasets.length === 0 && (
                    <option value="" disabled>-- no datasets available --</option>
                  )}
                  {datasets.length > 0 && (
                    <option value="">-- Select --</option>
                  )}
                  {datasets.map(d => <option key={d} value={d}>{d}</option>)}
                </select>
                {datasetsError && (
                  <p className="text-sm text-amber-200/90 border border-amber-700/50 rounded-md px-3 py-2 mt-2">
                    Could not load datasets — {datasetsError}
                  </p>
                )}
                {!datasetsError && datasets.length === 0 && (
                  <p className="text-sm text-zinc-500 italic border border-dashed border-zinc-800 rounded-md px-3 py-2 mt-2">
                    No local datasets available. Add a CSV file (or an image folder for the vision models) to the server's <span className="font-mono">data/</span> directory.
                  </p>
                )}
                {isReinforcementLearning && (
                  <p className="text-xs text-zinc-500 mt-1">Not required for reinforcement learning models.</p>
                )}
              </div>
            ) : (
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-zinc-400 mb-1">Hugging Face URL / Path</label>
                <input 
                  type="text" 
                  required
                  placeholder="e.g., databricks/databricks-dolly-15k"
                  value={payload.hf_dataset_url}
                  onChange={(e) => setPayload({...payload, hf_dataset_url: e.target.value})}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}
            
            <div>
              <label className="block text-sm font-medium text-zinc-400 mb-1">Target / Label Column</label>
              <input 
                type="text" 
                required
                value={payload.label_column}
                onChange={(e) => setPayload({...payload, label_column: e.target.value})}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
               <div>
                <label className="block text-sm font-medium text-zinc-400 mb-1">Test Size Split</label>
                <input 
                  type="number" 
                  step="0.01" min="0.01" max="0.99" required
                  value={payload.test_size}
                  onChange={(e) => setPayload({...payload, test_size: e.target.value})}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-blue-500"
                />
              </div>
               <div>
                <label className="block text-sm font-medium text-zinc-400 mb-1">Random State</label>
                <input 
                  type="number" 
                  required
                  value={payload.random_state}
                  onChange={(e) => setPayload({...payload, random_state: e.target.value})}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Section B: Model & Mode Selection */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
           <h2 className="text-lg font-semibold text-white mb-4 border-b border-zinc-800 pb-2">2. Architecture & Training Configuration</h2>
           
           <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
             <div>
                <label className="block text-sm font-medium text-zinc-400 mb-1">Model Selection</label>
                 <select 
                   required
                   value={payload.model_name}
                   onChange={(e) => setPayload({...payload, model_name: e.target.value})}
                   className="w-full bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-blue-500"
                 >
                   <option value="">-- Select Architecture --</option>
                   {models.map(m => <option key={m.name} value={m.name}>{m.name} ({m.category})</option>)}
                 </select>
                 {modelsError && (
                   <p className="text-sm text-amber-200/90 border border-amber-700/50 rounded-md px-3 py-2 mt-2">
                     Could not load models — {modelsError}. Using the built-in fallback list.
                   </p>
                 )}
              </div>

             <div>
               <label className="block text-sm font-medium text-zinc-400 mb-1">Training Mode</label>
               <select
                 value={payload.mode}
                 onChange={(e) => setPayload({...payload, mode: e.target.value})}
                 className="w-full bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-blue-500"
               >
                 {modeOptions.map(m => <option key={m} value={m}>{humanizeKey(m)}</option>)}
               </select>
               {modesError && (
                 <p className="text-xs text-amber-200/90 border border-amber-700/50 rounded-md px-3 py-2 mt-2">
                   Could not load the training modes — {modesError}. Using the built-in fallback list.
                 </p>
               )}
             </div>
           </div>

            {/* Mode Description */}
            {payload.mode !== 'manual' && (
              <div className="mb-6 p-3 bg-blue-900/20 border border-blue-700/50 rounded-md">
                <div className="text-sm text-blue-300">
                  <span className="font-semibold">Mode: {humanizeKey(payload.mode)}</span> - 
                  {modeDescription}
                </div>
              </div>
            )}

           {/* Preset Selector */}
           <div className="mb-6">
             <label className="block text-sm font-medium text-zinc-400 mb-1">Training Preset</label>
             <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
               {trainingPresets.map(p => (
                 <button
                   key={p.name}
                   type="button"
                   onClick={() => setPayload({...payload, preset: p.name})}
                   className={classNames(
                     "p-3 rounded-md border text-left transition-all",
                     payload.preset === p.name 
                       ? "bg-blue-900/40 border-blue-600 text-white" 
                       : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:border-zinc-600"
                   )}
                 >
                    <div className="font-medium capitalize text-sm">{p.name}</div>
                    <div className="text-xs text-zinc-500 mt-1">{p.description}</div>
                  </button>
                ))}
              </div>
              {presetsError && (
                <p className="text-sm text-amber-200/90 border border-amber-700/50 rounded-md px-3 py-2 mt-2">
                  Could not load training presets — {presetsError}. Using the built-in fallback list.
                </p>
              )}
            </div>

           {selectedModelDef?.category === 'reinforcement-learning' && (
             <div className="mb-6">
                <label className="block text-sm font-medium text-zinc-400 mb-1">Gymnasium Environment ID (Required for RL)</label>
                <input 
                  type="text" 
                  required
                  placeholder="e.g., CartPole-v1"
                  value={payload.env_id}
                  onChange={(e) => setPayload({...payload, env_id: e.target.value})}
                  className="w-full md:w-1/2 bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-blue-500"
                />
             </div>
           )}
        </div>

        {/* Section C: Model Details Panel */}
        {modelDetails && testResults && (
          <div className="bg-gradient-to-br from-blue-900/20 to-indigo-900/20 border border-blue-800/50 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">📊 Model Intelligence</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-zinc-950/50 rounded-md p-4 border border-zinc-800/50">
                <div className="text-xs text-zinc-400 uppercase tracking-wider mb-2">{testResults.accuracyLabel}</div>
                <div className="text-lg font-bold text-blue-400">
                  {testResults.accuracy ? `${(testResults.accuracy[0]*100).toFixed(0)}% - ${(testResults.accuracy[1]*100).toFixed(0)}%` : 'N/A'}
                </div>
              </div>

              <div className="bg-zinc-950/50 rounded-md p-4 border border-zinc-800/50">
                <div className="text-xs text-zinc-400 uppercase tracking-wider mb-2">Training Time</div>
                <div className="text-lg font-bold text-emerald-400">~{testResults.trainingTime}s</div>
              </div>

              <div className="bg-zinc-950/50 rounded-md p-4 border border-zinc-800/50">
                <div className="text-xs text-zinc-400 uppercase tracking-wider mb-2">Scalability</div>
                <div className={classNames("text-lg font-bold", 
                  testResults.scalability === 'high' ? 'text-emerald-400' :
                  testResults.scalability === 'medium' ? 'text-yellow-400' : 'text-orange-400'
                )}>
                  {testResults.scalability?.charAt(0).toUpperCase() + testResults.scalability?.slice(1)}
                </div>
              </div>

              <div className="bg-zinc-950/50 rounded-md p-4 border border-zinc-800/50">
                <div className="text-xs text-zinc-400 uppercase tracking-wider mb-2">Optimization Targets</div>
                <div className="text-sm text-zinc-300">
                  {selectedModelDef?.optimization?.length > 0 ? selectedModelDef.optimization.slice(0, 2).join(', ') : 'N/A'}
                  {selectedModelDef?.optimization?.length > 2 && '...'}
                </div>
              </div>
            </div>

            {testResults.bestFor && (
              <div className="mt-4 pt-4 border-t border-zinc-800/50">
                <div className="text-xs text-zinc-400 uppercase tracking-wider mb-2">Best For:</div>
                <div className="flex flex-wrap gap-2">
                  {testResults.bestFor.map((tag, idx) => (
                    <span key={idx} className="px-3 py-1 bg-blue-900/40 border border-blue-700/50 rounded-full text-xs text-blue-300">
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
          <div className="bg-amber-900/20 border border-amber-700/50 rounded-lg p-4 text-amber-200 text-sm">
            Could not load model details — {modelDetailsError}.
          </div>
        )}

        {/* Section D: Hyperparameters */}
        {selectedModelDef && payload.mode === 'manual' && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
             <h2 className="text-lg font-semibold text-white mb-4 border-b border-zinc-800 pb-2">3. Hyperparameters</h2>
             
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
                    <label className="block text-xs font-mono text-zinc-500 mb-1">{key}</label>
                    <input
                       type={isNumeric ? 'number' : 'text'}
                       step={step}
                       value={val === null || val === undefined ? '' : val}
                       onChange={(e) => handleParamChange(key, e.target.value)}
                       className="w-full bg-zinc-950 border border-zinc-800 rounded-md px-3 py-1.5 text-sm text-white focus:ring-2 focus:ring-blue-500"
                    />
                   </div>
                  );
                })}
              </div>
             ) : (
              <div className="text-sm text-zinc-500 italic">No configurable parameters required or auto-adjusted mode selected.</div>
             )}
          </div>
        )}

        {selectedModelDef && payload.mode !== 'manual' && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
             <h2 className="text-lg font-semibold text-white mb-4 border-b border-zinc-800 pb-2">3. Hyperparameters</h2>
             <div className="text-sm text-zinc-400">
               <p className="mb-2">
                 In <span className="font-semibold">{humanizeKey(payload.mode)}</span> mode, hyperparameters will be automatically {
                   payload.mode === 'auto_tune' ? 'tuned via grid search' :
                   payload.mode === 'auto_fine_tune' ? 'adapted with reduced learning rates' :
                   payload.mode === 'llm_fine_tune' ? 'suggested by Google Gemini' :
                   payload.mode === 'auto_search' ? 'optimized across model candidates' : 'configured'
                 }.
               </p>
               {payload.mode === 'auto_search' && (
                 <p className="mb-2">
                   {searchCandidates.length > 0 ? (
                     <>
                       Compared models: <span className="font-mono text-zinc-300">{searchCandidates.join(', ')}</span>
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

        <div className="flex justify-end pt-4">
          <button
            type="submit"
            disabled={submitting || !payload.model_name}
            className="flex items-center space-x-2 bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-md font-medium transition-colors disabled:opacity-50"
          >
            {submitting ? (
               <><Activity className="w-5 h-5 animate-spin" /><span>Initializing Run...</span></>
            ) : (
               <><Play className="w-5 h-5" /><span>Execute Training</span></>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};


// --- MAIN APP COMPONENT ---

const MainApp = () => {
  const { user, logout } = useContext(AuthContext);
  const [currentView, setCurrentView] = useState('runs');
  const [activeParams, setActiveParams] = useState(null);

  const navigate = useCallback((view, params = null) => {
    setCurrentView(view);
    setActiveParams(params);
  }, []);

  const renderView = () => {
    switch (currentView) {
      case 'models': return <ModelsCatalog />;
      case 'runs': return <RunsDashboard navigate={navigate} />;
      case 'run-details': return <RunDetails runId={activeParams} navigate={navigate} />;
      case 'new-job': return <NewJob navigate={navigate} />;
      default: return <RunsDashboard navigate={navigate} />;
    }
  };

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100 overflow-hidden font-sans">
      
      {/* Sidebar */}
      <aside className="w-64 bg-zinc-900 border-r border-zinc-800 flex flex-col hidden md:flex shrink-0">
        <div className="h-16 flex items-center px-6 border-b border-zinc-800 shrink-0">
          <Activity className="w-6 h-6 text-blue-500 mr-2" />
          <span className="font-bold text-lg tracking-tight">PrimeTrade</span>
        </div>
        <nav className="flex-1 px-4 py-6 space-y-2 overflow-y-auto">
          <SidebarItem 
            icon={Activity} label="Training Runs" 
            active={currentView === 'runs' || currentView === 'run-details'} 
            onClick={() => navigate('runs')} 
          />
          <SidebarItem 
            icon={Database} label="Model Catalog" 
            active={currentView === 'models'} 
            onClick={() => navigate('models')} 
          />
          <SidebarItem 
            icon={PlusCircle} label="New Job" 
            active={currentView === 'new-job'} 
            onClick={() => navigate('new-job')} 
          />
        </nav>
        <div className="p-4 border-t border-zinc-800 shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 truncate">
              <div className="w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center shrink-0">
                <User className="w-4 h-4 text-zinc-400" />
              </div>
              <div className="truncate text-sm">
                <div className="font-medium truncate">{user?.sub}</div>
                <div className="text-xs text-zinc-500 uppercase">{user?.role}</div>
              </div>
            </div>
            <button onClick={logout} className="p-2 text-zinc-400 hover:text-white rounded-md hover:bg-zinc-800 transition">
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-full overflow-hidden relative">
        {/* Mobile Header */}
        <header className="h-16 border-b border-zinc-800 bg-zinc-900 flex items-center px-4 md:hidden shrink-0">
           <Activity className="w-6 h-6 text-blue-500 mr-2" />
           <span className="font-bold text-lg tracking-tight">PrimeTrade</span>
        </header>

        <div className="flex-1 overflow-auto">
           <div className="p-6 md:p-10">
              {renderView()}
           </div>
        </div>
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