// Moved verbatim from App.jsx in R6 (Frontend UI redesign); only import/export wiring changed.
import React, { useState, useEffect, useContext, useRef } from 'react';
import { AuthContext, classNames } from '../components/shared.jsx';
import { isNumber, formatMetric, Bar } from '../components/metrics.jsx';

// Asking a model: the form is built from the schema of the run, so nobody has
// to know the columns by heart. What a model takes depends on its kind, and the
// server says which in ``request_kind``: a table row, some texts, a prompt, the
// last window of a series, node ids, the state of an agent, or an image.
export const PredictPanel = ({ runId }) => {
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
  // INVARIANT: both segmented buttons stay tabbable (no roving tabIndex) so
  // Tab reaches each one; refs are only used to move focus on arrow keys.
  const modeBtnRefs = useRef({});

  // DECISION: keep role="group" + aria-pressed (NOT radio/radiogroup) so the
  // existing getByRole('button') queries stay valid; clamp at the ends (no
  // wrap) and select-on-arrow. Events bubble from the focused button.
  const MODE_ORDER = ['form', 'json'];
  const handleSegmentedKeyDown = (e) => {
    const key = e.key;
    const HANDLED = ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'];
    if (!HANDLED.includes(key)) return;
    e.preventDefault();
    const focusedIdx = MODE_ORDER.findIndex((m) => modeBtnRefs.current[m] === document.activeElement);
    const currentIdx = focusedIdx >= 0 ? focusedIdx : MODE_ORDER.indexOf(mode);
    let nextIdx;
    if (key === 'Home') nextIdx = 0;
    else if (key === 'End') nextIdx = MODE_ORDER.length - 1;
    else if (key === 'ArrowRight' || key === 'ArrowDown') nextIdx = Math.min(currentIdx + 1, MODE_ORDER.length - 1);
    else nextIdx = Math.max(currentIdx - 1, 0);
    const nextMode = MODE_ORDER[nextIdx];
    setMode(nextMode);
    const el = modeBtnRefs.current[nextMode];
    if (el) el.focus();
  };

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
        // DECISION: invalid input is a client error, not a server error. Show
        // one friendly sentence here at the source so the raw SyntaxError
        // ("Unexpected token …") never reaches predict()'s server-message
        // path; server predict errors still surface verbatim via apiFetch.
        let rows;
        try {
          rows = JSON.parse(text);
        } catch {
          throw new Error('Rows must be valid JSON. Check the input and try again.');
        }
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
      <section className="panel predict-panel">
        <h2 className="mb-2">Use this model</h2>
        <p className="text-muted">{schemaError}</p>
      </section>
    );
  }
  if (!schema) return <section className="panel predict-panel"><p className="text-muted">Loading the model...</p></section>;

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
    <section className="panel predict-panel">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-1">
        <h2 className="whitespace-nowrap">Use this model</h2>
        {kind === 'rows' && (
          <div className="predict-segmented" role="group" aria-label="Input style" onKeyDown={handleSegmentedKeyDown}>
            {[['form', 'One row'], ['json', 'Several rows']].map(([m, label]) => (
              <button key={m} type="button" ref={(el) => { modeBtnRefs.current[m] = el; }} onClick={() => setMode(m)} aria-pressed={mode === m}
                className={classNames('predict-segmented-btn', mode === m ? 'bg-raised text-strong' : 'text-muted hover:text-strong')}>
                {label}
              </button>
            ))}
          </div>
        )}
      </div>
      {schema.output && <p className="text-sm text-muted mb-5">{schema.output.charAt(0).toUpperCase() + schema.output.slice(1)}.</p>}

      {kind === 'rows' && mode === 'form' && (
        <div className="predict-form-grid">
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

      <div className="predict-actions">
        <button onClick={predict} disabled={loading} className="btn btn-primary">{loading ? 'Working...' : (kind === 'prompt' ? 'Generate' : 'Predict')}</button>
        {kind === 'rows' && <span className="text-sm text-faint">A field left empty is treated as missing, as in training.</span>}
      </div>

      {error && <p role="alert" className="notice notice-bad mt-5 whitespace-pre-wrap">{error}</p>}
      {result && <PredictionResult result={result} />}
    </section>
  );
};

export const PredictionResult = ({ result }) => {
  const predictions = result.predictions || [];
  // Single screen-reader announcement per view: a short result summary only.
  // DECISION: the full result stays plain visible content; the status never
  // dumps probabilities or the whole payload.
  const formatOne = (p) => (Array.isArray(p) ? p.join(', ') : isNumber(p) ? formatMetric(p) : String(p));
  let summary = 'Prediction complete.';
  if (typeof result.text === 'string' && result.text) {
    summary = `Prediction complete: ${result.text.slice(0, 120)}`;
  } else if (result.action !== undefined) {
    const action = Array.isArray(result.action) ? result.action.join(', ') : String(result.action);
    summary = `Best action ${action}.`;
  } else if (predictions.length > 0) {
    summary = `${predictions.length} prediction${predictions.length === 1 ? '' : 's'}: ${formatOne(predictions[0])}`;
  } else if (result.reconstruction_error && result.reconstruction_error.length) {
    summary = `Reconstruction error ${formatMetric(result.reconstruction_error[0])}.`;
  }
  return (
    <div className="predict-result">
      <p role="status" className="sr-only">{summary}</p>
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
