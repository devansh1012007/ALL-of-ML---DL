import React, { useState, useEffect, useCallback, useContext } from 'react';
import { AdminScreen } from './AdminScreen';
import { formatBytes } from './format.js';
import { AuthContext, AuthProvider } from './components/shared.jsx';
import { AuthView } from './views/AuthView.jsx';
import { ModelsCatalog } from './views/ModelsCatalog.jsx';
import { RunsDashboard } from './views/RunsDashboard.jsx';
import { CompareRuns } from './views/CompareRuns.jsx';
import { RunDetails } from './views/RunDetails.jsx';
import { NewJob } from './views/NewJob.jsx';

// R6 split: the views moved verbatim to views/ and the shared + metrics
// pieces to components/; App.jsx keeps the shell and re-exports the moved
// views so the module surface (default App) is unchanged.
export { AuthView } from './views/AuthView.jsx';
export { ModelsCatalog } from './views/ModelsCatalog.jsx';
export { RunsDashboard } from './views/RunsDashboard.jsx';
export { CompareRuns } from './views/CompareRuns.jsx';
export { RunDetails } from './views/RunDetails.jsx';
export { NewJob } from './views/NewJob.jsx';
export { PredictPanel } from './views/PredictPanel.jsx';

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
          <nav aria-label="Main" data-shell="main-nav" className="flex flex-wrap items-center gap-1">
            {nav.map((item) => (
              <a
                key={item.id}
                href={`#/${item.id}`}
                aria-current={item.active ? 'page' : undefined}
                className="nav-link"
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
            <button onClick={logout} className="min-h-6 inline-flex items-center hover:text-strong underline-offset-4 hover:underline">Sign out</button>
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
