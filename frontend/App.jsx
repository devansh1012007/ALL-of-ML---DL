import React, { useState, useEffect, createContext, useContext, useCallback } from 'react';
import { 
  Activity, Database, Server, PlusCircle, LogOut, ChevronRight, 
  Play, CheckCircle, XCircle, Clock, Download, Lock, User
} from 'lucide-react';

// --- CONFIGURATION ---
const API_BASE = 'http://localhost:8010';

// --- UTILITIES ---
const parseJwt = (token) => {
  try {
    return JSON.parse(atob(token.split('.')[1]));
  } catch (e) {
    return null;
  }
};

const classNames = (...classes) => classes.filter(Boolean).join(' ');

// --- AUTH CONTEXT ---
const AuthContext = createContext(null);

const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(localStorage.getItem('prime_token'));
  const [user, setUser] = useState(token ? parseJwt(token) : null);

  const login = (newToken) => {
    localStorage.setItem('prime_token', newToken);
    setToken(newToken);
    setUser(parseJwt(newToken));
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
      logout();
      throw new Error("Session expired. Please log in again.");
    }
    
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP error! status: ${response.status}`);
    }
    
    // Artifact endpoint returns a file
    if (endpoint.endsWith('/artifact')) return response.blob();
    
    return response.json();
  }, [token, logout]);

  return (
    <AuthContext.Provider value={{ token, user, login, logout, apiFetch }}>
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
  const { login, apiFetch } = useContext(AuthContext);
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
      setError(err.message);
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
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-10 pr-4 py-2 bg-zinc-950 border border-zinc-800 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-white"
                placeholder="••••••••"
              />
            </div>
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

  useEffect(() => {
    apiFetch('/api/v1/ml/models').then(setModels).catch(console.error);
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

  const fetchRuns = useCallback(() => {
    apiFetch('/api/v1/ml/runs').then(setRuns).catch(console.error);
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
            {runs.length === 0 && (
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
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    apiFetch(`/api/v1/ml/runs/${runId}`).then(setRun).catch(console.error);
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

  if (!run) return <div className="text-zinc-500 p-8">Loading details...</div>;

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
                    <div className="text-xs text-zinc-500 uppercase tracking-wider mb-1">{key.replace('_', ' ')}</div>
                    <div className="text-xl font-mono text-zinc-200">
                      {typeof val === 'number' ? (Number.isInteger(val) ? val : val.toFixed(4)) : String(val)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-zinc-500">No metrics available yet.</p>
            )}
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Hyperparameters</h3>
            <pre className="bg-zinc-950 p-4 rounded-md text-sm text-zinc-400 font-mono overflow-x-auto border border-zinc-800/50">
              {JSON.stringify(run.hyperparameters, null, 2)}
            </pre>
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
  const [datasets, setDatasets] = useState([]);
  const [modelDetails, setModelDetails] = useState(null);
  const [trainingModes, setTrainingModes] = useState([]);
  const [trainingPresets, setTrainingPresets] = useState([]);
  
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
    apiFetch('/api/v1/ml/models').then(setModels).catch(console.error);
    apiFetch('/api/v1/ml/datasets').then(data => setDatasets(data.datasets || [])).catch(console.error);
    apiFetch('/api/v1/ml/training-modes').then(data => setTrainingModes(data.modes || [])).catch(console.error);
    apiFetch('/api/v1/ml/training-presets').then(data => setTrainingPresets(data.presets || [])).catch(console.error);
  }, [apiFetch]);

  const selectedModelDef = models.find(m => m.name === payload.model_name);
  const modeDescription = trainingModes[payload.mode] || '';
  const presetInfo = trainingPresets.find(p => p.name === payload.preset);

  // Fetch full model details when model changes
  useEffect(() => {
    if (payload.model_name) {
      apiFetch(`/api/v1/ml/model-details?model_name=${encodeURIComponent(payload.model_name)}`)
        .then(setModelDetails)
        .catch(console.error);
    } else {
      setModelDetails(null);
    }
  }, [payload.model_name, apiFetch]);

  // Auto-populate parameters when model changes
  useEffect(() => {
    if (selectedModelDef && payload.mode === 'manual') {
      setPayload(prev => ({ ...prev, hyperparameters: { ...selectedModelDef.parameters } }));
    }
  }, [payload.model_name, payload.mode, selectedModelDef]);

  const handleParamChange = (key, value) => {
    setPayload(prev => ({
      ...prev,
      hyperparameters: { ...prev.hyperparameters, [key]: value }
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    
    try {
      const submitPayload = { ...payload };
      if (sourceType === 'local') delete submitPayload.hf_dataset_url;
      if (sourceType === 'hf') delete submitPayload.dataset_name;

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
                <select 
                  required
                  value={payload.dataset_name}
                  onChange={(e) => setPayload({...payload, dataset_name: e.target.value})}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">-- Select --</option>
                  {datasets.map(d => <option key={d} value={d}>{d}</option>)}
                </select>
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
             </div>

             <div>
               <label className="block text-sm font-medium text-zinc-400 mb-1">Training Mode</label>
               <select 
                 value={payload.mode}
                 onChange={(e) => setPayload({...payload, mode: e.target.value})}
                 className="w-full bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-blue-500"
               >
                 <option value="manual">Manual (User-defined hyperparameters)</option>
                 <option value="auto_tune">Auto-Tune (Grid search optimization)</option>
                 <option value="auto_fine_tune">Auto Fine-Tune (Adaptive tuning)</option>
                 <option value="llm_fine_tune">LLM Fine-Tune (AI-guided parameters)</option>
                 <option value="auto_search">Auto Search (Bayesian optimization)</option>
               </select>
             </div>
           </div>

           {/* Mode Description */}
           {payload.mode !== 'manual' && (
             <div className="mb-6 p-3 bg-blue-900/20 border border-blue-700/50 rounded-md">
               <div className="text-sm text-blue-300">
                 <span className="font-semibold">Mode: {payload.mode.toUpperCase()}</span> - 
                 {payload.mode === 'auto_tune' && " Automatically searches for optimal hyperparameters using grid search."}
                 {payload.mode === 'auto_fine_tune' && " Adaptive fine-tuning with reduced learning rates for stability."}
                 {payload.mode === 'llm_fine_tune' && " Uses OpenAI to intelligently suggest optimal hyperparameters."}
                 {payload.mode === 'auto_search' && " Searches across multiple model candidates to find the best performer."}
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

        {/* Section D: Hyperparameters */}
        {selectedModelDef && payload.mode === 'manual' && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
             <h2 className="text-lg font-semibold text-white mb-4 border-b border-zinc-800 pb-2">3. Hyperparameters</h2>
             
             {Object.keys(payload.hyperparameters).length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {Object.entries(payload.hyperparameters).map(([key, val]) => (
                  <div key={key}>
                    <label className="block text-xs font-mono text-zinc-500 mb-1">{key}</label>
                    <input
                       type={typeof val === 'number' ? 'number' : 'text'}
                       step={typeof val === 'number' && !Number.isInteger(val) ? "0.0001" : "1"}
                       value={val === null ? '' : val}
                       onChange={(e) => {
                         let v = e.target.value;
                         if (typeof selectedModelDef.parameters[key] === 'number') v = Number(v);
                         handleParamChange(key, v);
                       }}
                       className="w-full bg-zinc-950 border border-zinc-800 rounded-md px-3 py-1.5 text-sm text-white focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                ))}
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
                 In <span className="font-semibold">{payload.mode}</span> mode, hyperparameters will be automatically {
                   payload.mode === 'auto_tune' ? 'tuned via grid search' :
                   payload.mode === 'auto_fine_tune' ? 'adapted with reduced learning rates' :
                   payload.mode === 'llm_fine_tune' ? 'suggested by OpenAI' :
                   payload.mode === 'auto_search' ? 'optimized across model candidates' : 'configured'
                 }.
               </p>
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