// Moved verbatim from App.jsx in R6 (Frontend UI redesign); only import/export wiring changed.
import React, { useState, useEffect, useCallback, useContext } from 'react';
import { AuthContext, StatusMark, classNames } from '../components/shared.jsx';
import { resultOf } from '../components/metrics.jsx';
import { timeAgo } from '../format.js';

export const RunsDashboard = ({ navigate }) => {
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
      .then(data => {
        // The real backend returns {items, total, limit, offset}; older callers
        // and mocks may still return a bare array. Accept both so the list is
        // not always empty against the real backend.
        const items = Array.isArray(data)
          ? data
          : Array.isArray(data?.items)
            ? data.items
            : [];
        setRuns(items);
        setRunsError(null);
      })
      .catch(err => { setRunsError(err.message || 'Unknown error'); });
  }, [apiFetch]);

  useEffect(() => {
    fetchRuns();
    // Aggressive polling to maintain accurate state
    const interval = setInterval(fetchRuns, 5000);
    return () => clearInterval(interval);
  }, [fetchRuns]);

  return (
    <div className="runs-page">
      <header className="page-header">
        <div>
          <h1 className="mb-1">Runs</h1>
          <p className="text-muted">Every training you started, and how it did against doing nothing.</p>
        </div>
        <div className="page-header-actions">
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
        <div className="runs-empty">
          <h2 className="mb-1">No runs yet</h2>
          <p className="text-muted mb-4">Pick a dataset and a model, and the first result appears here with its baseline.</p>
          <button onClick={() => navigate('new-job')} className="btn btn-primary">Start a run</button>
        </div>
      ) : (
        <div className="overflow-x-auto runs-table-wrap">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th scope="col" className="th">Compare</th>
                <th scope="col" className="th">Model</th>
                <th scope="col" className="th">Dataset</th>
                <th scope="col" className="th">Status</th>
                <th scope="col" className="th">Result</th>
                <th scope="col" className="th text-right">Started</th>
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
                        className="compare-check accent-[rgb(var(--accent))]"
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
