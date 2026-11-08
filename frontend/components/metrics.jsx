// Moved verbatim from App.jsx in R6 (Frontend UI redesign); only import/export wiring changed.
import React from 'react';
import { classNames } from './shared.jsx';

// --- METRICS, EVALUATION AND PREDICTION ---------------------------------------

// Metrics for which a smaller value is the better one.
export const LOWER_IS_BETTER = new Set(['mse', 'rmse', 'mae', 'smape', 'mase', 'reconstruction_mse', 'held_out_perplexity', 'davies_bouldin', 'train_loss']);
// The numbers of a run that are scores. Only those can be "the best": a larger
// training set or a higher baseline is not better.
export const SCORE_METRICS = new Set([
  'accuracy', 'val_accuracy', 'balanced_accuracy', 'f1_macro', 'precision_macro', 'recall_macro', 'roc_auc',
  'r2', 'mae', 'rmse', 'mse', 'smape', 'mase', 'rouge1', 'rouge2', 'rougeL', 'held_out_perplexity',
  'reconstruction_mse', 'reconstruction_r2', 'mean_return', 'success_rate', 'silhouette', 'davies_bouldin',
  'calinski_harabasz', 'trustworthiness', 'explained_variance', 'skill_vs_naive',
]);
// Metrics that are not a single number: they get a panel of their own instead
// of a tile (a tile would print "[object Object]").
export const STRUCTURED_METRICS = new Set([
  'model_parameters', 'cv', 'confusion_matrix', 'preprocessing', 'search_results',
]);
export const isNumber = (v) => typeof v === 'number' && Number.isFinite(v);

export const formatMetric = (val) => {
  if (val === null || val === undefined) return '—';
  if (typeof val === 'boolean') return val ? 'yes' : 'no';
  if (typeof val === 'number') return Number.isInteger(val) ? String(val) : fmtNum(val);
  return String(val);
};

// What the list shows for a run: the score, and the baseline it has to beat.
// ``beatsBaseline`` is null when the run has no baseline to compare with.
export const resultOf = (run) => {
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
export const fmtNum = (v) => {
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
export const headlineOf = (m) => {
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
export const ResultLine = ({ metrics }) => {
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
    <section aria-label="Result" className="panel result-panel">
      <div className="result-headline-row">
        <span className="result-value">{fmtNum(h.value)}</span>
        <span className="text-muted">{h.label}{h.higherBetter ? '' : ', lower is better'}</span>
      </div>
      {sentence && <p className={classNames('mt-2', better === false ? 'text-warn' : 'text-ink')}>{sentence}</p>}

      {hasBase && (
        <div className="result-scale" role="img" aria-label={description}>
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
        <div className="result-scale-range">
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
export const OTHER_SCORES = [
  ['balanced_accuracy', 'Balanced accuracy'], ['f1_macro', 'F1 (macro)'], ['roc_auc', 'ROC AUC'],
  ['r2', 'R²'], ['mae', 'MAE'], ['rmse', 'RMSE'], ['smape', 'sMAPE %'], ['rouge2', 'ROUGE-2'], ['rougeL', 'ROUGE-L'],
  ['skill_vs_naive', 'Skill vs naive'], ['mean_return', 'Average return'], ['success_rate', 'Success rate'],
];

export const EvaluationPanel = ({ metrics }) => {
  const headline = headlineOf(metrics);
  const shown = OTHER_SCORES.filter(([key]) => isNumber(metrics[key]) && !(headline && headline.key === key));
  return (
    <>
      <ResultLine metrics={metrics} />
      {shown.length > 0 && (
        <section className="panel eval-panel">
          <h2 className="mb-4">Other scores</h2>
          <dl className="eval-scores">
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

export const Bar = ({ label, value, max, tone = 'bg-accent', note }) => {
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

export const ConfusionMatrix = ({ confusion }) => {
  if (!confusion || !Array.isArray(confusion.matrix) || confusion.matrix.length === 0) return null;
  const labels = confusion.labels || [];
  const top = Math.max(1, ...confusion.matrix.flat());
  return (
    <section className="panel confusion-panel">
      <h2 className="mb-1">Where it gets confused</h2>
      <p className="text-sm text-muted mb-5">Rows are the true class, columns the predicted one. The diagonal is correct.</p>
      <div className="confusion-wrap">
        <table className="confusion-table">
          <thead>
            <tr>
              <th scope="col" className="px-3 py-2" />
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
export const PreprocessingReport = ({ report }) => {
  if (!report) return null;
  const list = (items) => (items && items.length ? items.join(', ') : 'none');
  return (
    <section className="panel prep-panel">
      <h2 className="mb-4">How the data was prepared</h2>
      <dl className="detail-list detail-list-wide">
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
