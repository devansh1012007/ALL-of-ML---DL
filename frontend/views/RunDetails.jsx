// Moved verbatim from App.jsx in R6 (Frontend UI redesign); only import/export wiring changed.
import React, { useState, useEffect, useRef, useContext } from 'react';
import { AuthContext, StatusMark, Breadcrumb, RUN_POLL_INTERVAL_MS } from '../components/shared.jsx';
import { STRUCTURED_METRICS, isNumber, formatMetric, fmtNum, EvaluationPanel, ConfusionMatrix, PreprocessingReport } from '../components/metrics.jsx';
import { PredictPanel } from './PredictPanel.jsx';
import { timeAgo, formatWhen } from '../format.js';

export const RunEvents = ({ runId }) => {
  const { apiFetch } = useContext(AuthContext);
  const [events, setEvents] = useState([]);
  const [runStatus, setRunStatus] = useState(null);
  // Single screen-reader announcement per view: the latest phase only.
  // DECISION: log lines are plain visible content; announcing every polled
  // line would spam screen readers. The status text changes only when the
  // phase string changes, so repeated same-phase polls never re-announce.
  const [announcedPhase, setAnnouncedPhase] = useState('');
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

  // The phase an event carries, from its kind / payload.phase. Metric and
  // message events carry no phase and never update the announcement.
  const phaseOf = (event) => {
    const payload = event.payload || {};
    if (event.kind === 'phase' && payload.phase) return String(payload.phase);
    if (payload.phase) return String(payload.phase);
    return null;
  };
  let latestPhase = null;
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const phase = phaseOf(events[i]);
    if (phase) {
      latestPhase = phase;
      break;
    }
  }

  // Dedup by phase string: the status updates only on a phase change, so
  // repeated same-phase polls keep the same text and never re-announce.
  useEffect(() => {
    if (latestPhase && latestPhase !== announcedPhase) {
      setAnnouncedPhase(latestPhase);
    }
  }, [latestPhase, announcedPhase]);

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
      {announcedPhase && (
        <p role="status" className="sr-only">{announcedPhase}</p>
      )}
      <ol className="max-h-56 overflow-y-auto text-sm space-y-1 tabular-nums">
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

export const RunDetails = ({ runId, navigate }) => {
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
        <Breadcrumb items={[{ label: 'Runs', href: '#/runs' }, { label: `#${runId}` }]} />
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
  // INVARIANT: seconds is null unless both timestamps parse; a NaN diff
  // (garbage-but-truthy dates) must hide the chip, never render "Took NaN s".
  // 0 is a valid duration (finished == started), so never use falsiness here.
  const durationMs = run.started_at && run.finished_at
    ? new Date(run.finished_at) - new Date(run.started_at)
    : null;
  const seconds = durationMs === null || Number.isNaN(durationMs)
    ? null
    : Math.max(0, Math.round(durationMs / 1000));
  const scalarMetrics = run.metrics
    ? Object.entries(run.metrics).filter(([k, v]) => !STRUCTURED_METRICS.has(k) && !k.startsWith('_') && (v === null || typeof v !== 'object'))
    : [];

  return (
    <div className="run-details-page">
      <Breadcrumb items={[{ label: 'Runs', href: '#/runs' }, { label: `#${run.id}` }]} />

      <header className="page-header">
        <div>
          <h1 className="mb-1">{run.model_name}</h1>
          <p className="text-muted flex flex-wrap items-center gap-x-5 gap-y-1">
            <StatusMark status={run.status} />
            <span>{run.dataset_tag}</span>
            <span title={formatWhen(run.created_at)}>Started {timeAgo(run.created_at)}</span>
            {seconds !== null && <span className="tabular-nums">Took {seconds} s</span>}
          </p>
        </div>
        <div className="page-header-actions">
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
        <section className="panel metrics-panel">
          <details>
            <summary className="disclosure-summary cursor-pointer text-strong font-medium hover:text-accent"><span aria-hidden="true" className="disclosure-marker">+</span>All metrics ({scalarMetrics.length})</summary>
            <dl className="mt-4 metrics-grid">
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

      <section className="panel training-panel">
        <h2 className="mb-4">How it was trained</h2>
        <dl className="detail-list">
          <dt className="text-muted">Data source</dt><dd className="capitalize">{run.dataset_source}</dd>
          <dt className="text-muted">Dataset</dt><dd className="break-all">{run.dataset_tag}</dd>
          {run.hf_dataset_url && (<><dt className="text-muted">Hugging Face</dt><dd><a href={run.hf_dataset_url} target="_blank" rel="noreferrer" className="link break-all">{run.hf_dataset_url}</a></dd></>)}
          {run.mode && (<><dt className="text-muted">Mode</dt><dd className="capitalize">{run.mode}</dd></>)}
          {run.env_id && (<><dt className="text-muted">Environment</dt><dd className="break-all">{run.env_id}</dd></>)}
        </dl>
        <details className="mt-6">
          <summary className="disclosure-summary cursor-pointer text-strong font-medium hover:text-accent"><span aria-hidden="true" className="disclosure-marker">+</span>Parameters</summary>
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
