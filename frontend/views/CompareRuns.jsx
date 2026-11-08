// Moved verbatim from App.jsx in R6 (Frontend UI redesign); only import/export wiring changed.
import React, { useState, useEffect, useContext } from 'react';
import { AuthContext, classNames, Breadcrumb } from '../components/shared.jsx';
import { LOWER_IS_BETTER, SCORE_METRICS, STRUCTURED_METRICS, isNumber, formatMetric, Bar } from '../components/metrics.jsx';

// Several runs side by side: the same metric in a row, the best value marked,
// and a bar so the difference is visible without reading the numbers.
export const CompareRuns = ({ runIds, navigate }) => {
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
    <div className="compare-page">
      <Breadcrumb items={[{ label: 'Runs', href: '#/runs' }, { label: 'Compare' }]} />

      <header className="page-header">
        <div>
          <h1 className="mb-1">Compare {runs.length} runs</h1>
          <p className="text-muted">The same score side by side. The best value in each row is marked.</p>
        </div>
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
        <section className="panel compare-chart-panel">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
            <h2>By metric</h2>
            <label htmlFor="compare-metric" className="flex items-center gap-3 text-sm text-muted">
              Metric
              <select id="compare-metric" value={selected} onChange={(e) => setMetric(e.target.value)} className="field w-auto">
                {choices.map((n) => <option key={n} value={n}>{n.replace(/_/g, ' ')}</option>)}
              </select>
            </label>
          </div>
          <div className="compare-chart">
            {completed.map((r) => {
              const value = valueOf(r, selected);
              const isBest =
                value !== null && bestOf(selected) !== null && value === bestOf(selected);
              return (
                <Bar
                  key={r.id}
                  label={`#${r.id} ${r.model_name}`}
                  value={value}
                  max={top}
                  tone={isBest ? 'bg-accent' : 'bg-faint'}
                  note={isBest ? 'best' : undefined}
                />
              );
            })}
          </div>
          <p className="text-sm text-faint mt-4">{LOWER_IS_BETTER.has(selected) ? 'Lower is better.' : 'Higher is better.'}</p>
        </section>
      )}

      <section className="panel compare-table-wrap">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th scope="col" className="th">Metric</th>
              {completed.map((r) => (
                <th scope="col" key={r.id} className="th">
                  <button onClick={() => navigate('run-details', r.id)} className="compare-run-link text-strong hover:text-accent font-medium">
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
