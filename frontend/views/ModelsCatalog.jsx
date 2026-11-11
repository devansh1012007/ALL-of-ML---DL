// Moved verbatim from App.jsx in R6 (Frontend UI redesign); only import/export wiring changed.
import React, { useState, useEffect, useContext } from 'react';
import { AuthContext, classNames, FALLBACK_MODELS, MODEL_GROUPS, DATASET_KIND_LABELS } from '../components/shared.jsx';

export const ModelsCatalog = () => {
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
    <div className="catalog-page">
      <header className="page-header">
        <div>
          <h1 className="mb-1">Models</h1>
          <p className="text-muted">
            {modelsError
              ? 'The model list could not be loaded, so what this server supports is unknown. Showing the built-in list instead.'
              : models.length > 0 ? `${runnable} of ${models.length} can run on this server.` : 'What you can train, and what this server can run.'}
          </p>
        </div>
        <input
          type="search" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="Find a model" aria-label="Find a model" className="field catalog-search"
        />
      </header>

      {modelsError && (
        <p role="alert" className="notice notice-bad">
          The model list could not be loaded ({modelsError}). Showing the built-in list instead.
        </p>
      )}

      {groups.length === 0 && <p className="text-muted">No model matches that search.</p>}

      {groups.map(([label, rows]) => (
        <section key={label} className="catalog-group">
          <h2 className="catalog-group-title">{label}</h2>
          <ul className="catalog-list">
            {rows.map((model) => {
              const usable = model.implemented !== false && model.available !== false;
              const result = usable ? expectedResult(model.test_results) : null;
              const parameters = Object.entries(model.parameters || {});
              return (
                <li key={model.name} className="model-row">
                  <details className="group">
                    <summary className="disclosure-summary model-summary flex items-baseline gap-4 py-3 cursor-pointer list-none [&::-webkit-details-marker]:hidden hover:bg-surface/60 px-2 rounded">
                      <span aria-hidden="true" className="disclosure-marker">+</span>
                      <span className="model-name font-medium text-strong break-words">{model.name}</span>
                      <span className="model-desc text-muted line-clamp-1 group-open:line-clamp-none">{model.description}</span>
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
                      <dl className="model-detail-grid">
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
