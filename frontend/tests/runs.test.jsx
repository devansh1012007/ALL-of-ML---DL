import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { screen, cleanup, act, waitFor, fireEvent } from '@testing-library/react';
import { renderApp } from './helpers.jsx';

let backend;

beforeEach(() => {
  vi.useRealTimers();
  window.localStorage.clear();
  window.location.hash = '';
});

afterEach(() => {
  cleanup();
  if (backend && backend.restore) backend.restore();
  backend = undefined;
  window.localStorage.clear();
  window.location.hash = '';
  vi.useRealTimers();
});

function completedRun(id, modelName) {
  return {
    id,
    model_name: modelName,
    dataset_source: 'local',
    dataset_tag: 'fake.csv',
    dataset_id: 1,
    mode: 'manual',
    env_id: null,
    optimize_metric: 'accuracy',
    model_candidates: null,
    status: 'completed',
    job_kind: 'train',
    artifact_path: 'models/fake.joblib',
    artifact_removed: false,
    metrics: null,
    tags: [],
    note: null,
    created_at: '2026-11-08T00:00:00Z',
    updated_at: '2026-11-08T00:00:00Z',
    started_at: '2026-11-08T00:00:00Z',
    finished_at: '2026-11-08T00:01:00Z',
    wall_seconds: 60,
  };
}

function runningRun(id, modelName) {
  return {
    ...completedRun(id, modelName),
    status: 'running',
    artifact_path: null,
    metrics: null,
  };
}

describe('runs: backend envelope renders rows', () => {
  it('{items} response renders the run row (real backend shape)', async () => {
    const app = renderApp({
      hash: '#/runs',
      token: 'testuser',
      seed: {
        runs: [completedRun(7, 'Envelope_Forest')],
      },
    });
    backend = app.backend;

    expect(await screen.findByText('Envelope_Forest')).toBeInTheDocument();
    expect(screen.getByText('#7')).toBeInTheDocument();
    expect(screen.getByText('fake.csv')).toBeInTheDocument();
    expect(screen.queryByText('No runs yet')).not.toBeInTheDocument();
  });
});

describe('runs: bare array tolerance', () => {
  it('bare array response still renders the run row', async () => {
    const bareRuns = [completedRun(9, 'Bare_Array_Model')];
    const app = renderApp({
      hash: '#/models',
      token: 'testuser',
      seed: {
        runs: [completedRun(9, 'Bare_Array_Model')],
      },
    });
    backend = app.backend;

    // The harness always answers /api/v1/ml/runs with {items,...}; simulate the
    // older bare-array shape by wrapping fetch before navigating to runs.
    const fakeFetch = global.fetch;
    global.fetch = async (input, options) => {
      const rawUrl =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input && input.url
              ? input.url
              : String(input);
      let pathname = rawUrl;
      try {
        pathname = new URL(rawUrl, 'http://localhost:8010').pathname;
      } catch {
        // leave rawUrl as-is for the delegate
      }
      if (pathname === '/api/v1/ml/runs') {
        return {
          ok: true,
          status: 200,
          json: async () => JSON.parse(JSON.stringify(bareRuns)),
          text: async () => JSON.stringify(bareRuns),
          blob: async () =>
            new Blob([JSON.stringify(bareRuns)], {
              type: 'application/json',
            }),
        };
      }
      return fakeFetch(input, options);
    };

    await act(async () => {
      window.location.hash = '#/runs';
      window.dispatchEvent(new Event('hashchange'));
    });

    expect(await screen.findByText('Bare_Array_Model')).toBeInTheDocument();
    expect(screen.getByText('#9')).toBeInTheDocument();
    expect(screen.queryByText('No runs yet')).not.toBeInTheDocument();
  });
});

describe('runs: checkbox column purpose is perceivable', () => {
  it('Runs header shows visible "Compare" text and keeps row labels', async () => {
    const app = renderApp({
      hash: '#/runs',
      token: 'testuser',
      seed: {
        runs: [completedRun(7, 'Envelope_Forest')],
      },
    });
    backend = app.backend;

    expect(await screen.findByText('Envelope_Forest')).toBeInTheDocument();

    const header = screen.getByRole('columnheader', { name: /compare/i });
    expect(header).toHaveTextContent('Compare');
    // Visible, not screen-reader-only: the header cell holds no sr-only text.
    expect(header.querySelector('.sr-only')).toBeNull();
    expect(header.className).not.toContain('sr-only');

    // Row checkboxes keep their comparison labels.
    expect(
      screen.getByLabelText(/select run 7 for a comparison/i)
    ).toBeInTheDocument();
  });
});

describe('run details: Progress announces the latest phase only', () => {
  it(
    'single role=status with latest phase; same-phase poll is stable, phase change updates',
    async () => {
      const app = renderApp({
        hash: '#/run-details/1',
        token: 'testuser',
        seed: {
          runs: [runningRun(1, 'Running_Forest')],
          events: {
            1: {
              events: [
                {
                  seq: 1,
                  kind: 'phase',
                  payload: { phase: 'preprocessing', epoch: 1 },
                },
              ],
            },
          },
        },
      });
      backend = app.backend;

      expect(
        await screen.findByRole('heading', { name: /progress/i })
      ).toBeInTheDocument();

      // The log itself is plain content now, not a live region.
      const progress = document.querySelector(
        'section[aria-label="Progress"]'
      );
      expect(progress).not.toBeNull();
      const log = progress.querySelector('ol');
      expect(log).not.toBeNull();
      expect(log).not.toHaveAttribute('aria-live');
      expect(log).toHaveTextContent('epoch 1');

      // Exactly one status, carrying the phase only (not the epoch detail).
      const statuses = screen.getAllByRole('status');
      expect(statuses).toHaveLength(1);
      const status = statuses[0];
      expect(status).toHaveTextContent('preprocessing');
      expect(status.textContent).not.toMatch(/epoch/);
      const stableText = status.textContent;

      // A repeated same-phase poll (different detail, same phase) must not
      // re-announce: the status text stays stable while the log grows.
      backend.state.events['1'].events.push({
        seq: 2,
        kind: 'phase',
        payload: { phase: 'preprocessing', epoch: 2 },
      });
      await waitFor(
        () => {
          expect(log).toHaveTextContent('epoch 2');
        },
        { timeout: 8000 }
      );
      expect(screen.getAllByRole('status')).toHaveLength(1);
      expect(screen.getByRole('status')).toHaveTextContent('preprocessing');
      expect(screen.getByRole('status').textContent).toBe(stableText);
      expect(screen.getByRole('status').textContent).not.toMatch(/epoch/);

      // A metric line must not become the announcement either.
      backend.state.events['1'].events.push({
        seq: 3,
        kind: 'metric',
        payload: { accuracy: 0.95 },
      });
      await waitFor(
        () => {
          expect(log).toHaveTextContent('accuracy 0.95');
        },
        { timeout: 8000 }
      );
      expect(screen.getByRole('status')).toHaveTextContent('preprocessing');
      expect(screen.getByRole('status').textContent).toBe(stableText);

      // A phase change updates the single status.
      backend.state.events['1'].events.push({
        seq: 4,
        kind: 'phase',
        payload: { phase: 'training' },
      });
      await waitFor(
        () => {
          expect(screen.getByRole('status')).toHaveTextContent('training');
        },
        { timeout: 8000 }
      );
      expect(screen.getAllByRole('status')).toHaveLength(1);
      expect(screen.getByRole('status').textContent.trim()).toBe('training');
    },
    { timeout: 30000 }
  );
});

describe('runs: R3a empty state + select-for-compare', () => {
  it('empty history uses the shared empty panel with the pinned copy', async () => {
    const app = renderApp({
      hash: '#/runs',
      token: 'testuser',
      seed: { runs: [] },
    });
    backend = app.backend;

    expect(await screen.findByText('No runs yet')).toBeInTheDocument();
    // R3a shared empty-state class (absent before the redesign).
    const empty = document.querySelector('.runs-empty');
    expect(empty).not.toBeNull();
    expect(empty).toHaveTextContent('Pick a dataset and a model, and the first result appears here with its baseline.');

    // New run actions stay available from the header and the empty state.
    expect(screen.getByRole('button', { name: /^new run$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /start a run/i })).toBeInTheDocument();
    const compare = screen.getByRole('button', { name: /^compare$/i });
    expect(compare).toBeDisabled();
  });

  it('ticking two runs enables Compare and navigates to the compare view', async () => {
    const app = renderApp({
      hash: '#/runs',
      token: 'testuser',
      seed: {
        runs: [completedRun(7, 'Compare_Forest'), completedRun(8, 'Compare_Linear')],
      },
    });
    backend = app.backend;

    expect(await screen.findByText('Compare_Forest')).toBeInTheDocument();

    // R3a shared checkbox class (absent before the redesign).
    const boxes = document.querySelectorAll('.compare-check');
    expect(boxes).toHaveLength(2);

    const compare = screen.getByRole('button', { name: /^compare$/i });
    expect(compare).toBeDisabled();

    fireEvent.click(screen.getByLabelText(/select run 7 for a comparison/i));
    expect(
      screen.getByRole('button', { name: /^compare \(1\)$/i })
    ).toBeDisabled();

    fireEvent.click(screen.getByLabelText(/select run 8 for a comparison/i));
    const enabled = screen.getByRole('button', { name: /^compare \(2\)$/i });
    expect(enabled).not.toBeDisabled();
    expect(enabled).toHaveAttribute('title', 'Tick two to four completed runs');

    fireEvent.click(enabled);
    // navigate() URL-encodes the joined ids ("7+8" -> "7%2B8"); readHash decodes it.
    expect(window.location.hash).toBe('#/compare/7%2B8');
  });
});

function completedDetail(id, modelName) {
  return {
    ...completedRun(id, modelName),
    dataset_hash: 'abc123',
    label_column: 'label',
    random_state: 42,
    test_size: 0.2,
    task_type: 'classification',
    metrics: {
      accuracy: 0.9,
      baseline_accuracy: 0.5,
      f1_macro: 0.87,
      artifact_kind: 'tabular',
      confusion_matrix: { labels: ['a', 'b'], matrix: [[4, 1], [2, 3]] },
      preprocessing: {
        numeric_columns: ['age'],
        categorical_columns: ['f2'],
        missing_cells_imputed: 5,
        rows_dropped_missing_label: 2,
        scaled: true,
        task_type_source: 'request',
      },
      model_parameters: { n_estimators: 50 },
    },
    hyperparameters: { n_estimators: 50 },
    has_charts: false,
    heartbeat_at: null,
  };
}

describe('run details: R3b sections with shared layout hooks', () => {
  it('completed run renders result stack, training facts, and predict with one status after predict (C2)', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: {
        runs: [completedRun(1, 'Detail_Forest')],
        runDetails: { 1: completedDetail(1, 'Detail_Forest') },
      },
    });
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /detail_forest/i })
    ).toBeInTheDocument();
    // Result stack: headline, other scores, confusion, preprocessing, training, predict.
    const result = document.querySelector('section[aria-label="Result"]');
    expect(result).not.toBeNull();
    expect(result).toHaveTextContent('0.900');
    expect(
      screen.getByRole('heading', { name: /^other scores$/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /where it gets confused/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /how the data was prepared/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /how it was trained/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /^use this model$/i })
    ).toBeInTheDocument();
    expect(screen.getByText('Data source')).toBeInTheDocument();
    expect(screen.getByText('Dataset')).toBeInTheDocument();

    // R3b shared layout hooks (absent before the redesign).
    expect(document.querySelector('.run-details-page')).not.toBeNull();
    expect(document.querySelector('.result-panel')).not.toBeNull();
    expect(document.querySelector('.result-value')).not.toBeNull();
    expect(document.querySelector('.result-scale')).not.toBeNull();
    expect(document.querySelector('.eval-scores')).not.toBeNull();
    expect(document.querySelector('.confusion-wrap')).not.toBeNull();
    // Two stacking definition lists: preparation (wide) + training facts.
    expect(document.querySelectorAll('.detail-list')).toHaveLength(2);
    expect(document.querySelector('.detail-list-wide')).not.toBeNull();
    expect(document.querySelector('.predict-panel')).not.toBeNull();
    expect(document.querySelector('.predict-segmented')).not.toBeNull();
    expect(document.querySelector('.predict-form-grid')).not.toBeNull();

    // C2: exactly one status after predict, and no other live region.
    fireEvent.click(screen.getByRole('button', { name: /^predict$/i }));
    expect(await screen.findByRole('status')).toBeInTheDocument();
    const statuses = screen.getAllByRole('status');
    expect(statuses).toHaveLength(1);
    expect(statuses[0]).toHaveTextContent(/1 prediction/);
    expect(document.querySelectorAll('[aria-live]')).toHaveLength(0);
  });
});

describe('runs: R5 mobile/a11y hardening (scroll shell, table scope, focus order)', () => {
  it('runs table scrolls in its wrapper, headers declare scope, and compare selection precedes the model link in tab order', async () => {
    const app = renderApp({
      hash: '#/runs',
      token: 'testuser',
      seed: {
        runs: [completedRun(7, 'R5_Forest')],
      },
    });
    backend = app.backend;

    expect(await screen.findByText('R5_Forest')).toBeInTheDocument();

    // The wrapper owns horizontal scrolling at 390px (the min-width itself
    // lives in CSS and is guarded in static.test.js: jsdom cannot measure it).
    const wrap = document.querySelector('.runs-table-wrap');
    expect(wrap).not.toBeNull();
    expect(wrap.className).toContain('overflow-x-auto');

    // Column headers declare their scope for screen readers (absent pre-R5).
    const headers = wrap.querySelectorAll('th');
    expect(headers.length).toBeGreaterThan(0);
    headers.forEach((th) => {
      expect(th).toHaveAttribute('scope', 'col');
    });

    // Tab order follows DOM order: checkbox, then the model link. Both are
    // keyboard-focusable; the model link is the sole activation path (the
    // mouse-only row click handler was removed in B1/D-B1).
    const checkbox = screen.getByLabelText(/select run 7 for a comparison/i);
    const link = screen.getByRole('link', { name: /r5_forest/i });
    expect(
      checkbox.compareDocumentPosition(link) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    checkbox.focus();
    expect(document.activeElement).toBe(checkbox);
    link.focus();
    expect(document.activeElement).toBe(link);
  });
});

describe('runs: B1 link-based row activation (D-B1)', () => {
  it('clicking the row (not the link) does not navigate; the model link does', async () => {
    const app = renderApp({
      hash: '#/runs',
      token: 'testuser',
      seed: {
        runs: [completedRun(7, 'B1_Forest')],
      },
    });
    backend = app.backend;

    expect(await screen.findByText('B1_Forest')).toBeInTheDocument();
    expect(window.location.hash).toBe('#/runs');

    // (a) Row click is inert by design (D-B1): the model link is the sole
    // activation path, so a click on the tr must not change the hash.
    const row = screen
      .getByLabelText(/select run 7 for a comparison/i)
      .closest('tr');
    expect(row).not.toBeNull();
    fireEvent.click(row);
    expect(window.location.hash).toBe('#/runs');

    // (b) The model link navigates to the run-details view. The link is a
    // plain <a href> (browser-default navigation), which jsdom processes
    // asynchronously, so wait for the hash to catch up.
    const link = screen.getByRole('link', { name: /b1_forest/i });
    fireEvent.click(link);
    await waitFor(
      () => {
        expect(window.location.hash).toBe('#/run-details/7');
      },
      { timeout: 3000 }
    );
  });

  it('checkbox still toggles selection and enables Compare after row-click removal', async () => {
    const app = renderApp({
      hash: '#/runs',
      token: 'testuser',
      seed: {
        runs: [
          completedRun(7, 'B1_Check_Forest'),
          completedRun(8, 'B1_Check_Linear'),
        ],
      },
    });
    backend = app.backend;

    expect(await screen.findByText('B1_Check_Forest')).toBeInTheDocument();

    const compare = screen.getByRole('button', { name: /^compare$/i });
    expect(compare).toBeDisabled();

    fireEvent.click(screen.getByLabelText(/select run 7 for a comparison/i));
    expect(
      screen.getByLabelText(/select run 7 for a comparison/i)
    ).toBeChecked();

    fireEvent.click(screen.getByLabelText(/select run 8 for a comparison/i));
    const enabled = screen.getByRole('button', { name: /^compare \(2\)$/i });
    expect(enabled).not.toBeDisabled();

    // Untick: selection (and the Compare count) updates, no navigation.
    fireEvent.click(screen.getByLabelText(/select run 7 for a comparison/i));
    expect(
      screen.getByLabelText(/select run 7 for a comparison/i)
    ).not.toBeChecked();
    expect(
      screen.getByRole('button', { name: /^compare \(1\)$/i })
    ).toBeDisabled();
    expect(window.location.hash).toBe('#/runs');
  });
});

describe('runs: B2 Started tooltip uses formatWhen NaN guard (A1)', () => {
  it('garbage created_at shows "—" cell and "—" title (no Invalid Date leak)', async () => {
    const app = renderApp({
      hash: '#/runs',
      token: 'testuser',
      seed: {
        runs: [{ ...completedRun(7, 'B2_Forest'), created_at: 'garbage' }],
      },
    });
    backend = app.backend;

    expect(await screen.findByText('B2_Forest')).toBeInTheDocument();

    // The Started td is the last cell of the row; assert both its text and
    // its title tooltip use the "—" unknown sentinel, not "Invalid Date".
    const row = screen
      .getByLabelText(/select run 7 for a comparison/i)
      .closest('tr');
    expect(row).not.toBeNull();
    const cells = row.querySelectorAll('td');
    const startedCell = cells[cells.length - 1];
    expect(startedCell).toHaveTextContent('—');
    expect(startedCell).toHaveAttribute('title', '—');
    expect(startedCell.getAttribute('title')).not.toMatch(/Invalid Date/);
  });
});

// Phase E: RunDetails Started tooltip must use the formatWhen NaN guard.
describe('run details: Phase E Started tooltip NaN guard', () => {
  it('garbage created_at shows "—" tooltip and text (no Invalid Date leak)', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: {
        runs: [completedRun(1, 'Detail_E_Forest')],
        runDetails: { 1: { ...completedDetail(1, 'Detail_E_Forest'), created_at: 'garbage' } },
      },
    });
    backend = app.backend;

    await screen.findByRole('heading', { name: /detail_e_forest/i });

    // The Started span carries the tooltip; assert title and text both use
    // the "—" unknown sentinel, not "Invalid Date".
    const started = screen.getByText(/^started/i);
    expect(started).toHaveAttribute('title', '—');
    expect(started).toHaveTextContent('—');
    expect(started.getAttribute('title')).not.toMatch(/Invalid Date/);
  });
});

// Phase P3: "Took NaN s" must never leak when run timestamps are garbage.
describe('run details: P3 duration NaN guard', () => {
  it('garbage started/finished hides the duration chip (no Took, no NaN)', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: {
        runs: [completedRun(1, 'Detail_P3_Garbage')],
        runDetails: {
          1: {
            ...completedDetail(1, 'Detail_P3_Garbage'),
            started_at: 'garbage',
            finished_at: 'garbage',
          },
        },
      },
    });
    backend = app.backend;

    await screen.findByRole('heading', { name: /detail_p3_garbage/i });

    // The bug renders "Took NaN s"; the fix hides the chip entirely.
    expect(screen.queryByText(/took/i)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/NaN/);
  });

  it('valid zero duration still renders "Took 0 s"', async () => {
    const ts = '2026-11-08T00:00:00Z';
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: {
        runs: [completedRun(1, 'Detail_P3_Zero')],
        runDetails: {
          1: {
            ...completedDetail(1, 'Detail_P3_Zero'),
            started_at: ts,
            finished_at: ts,
          },
        },
      },
    });
    backend = app.backend;

    await screen.findByRole('heading', { name: /detail_p3_zero/i });

    // finished == started must still render "Took 0 s" (not hidden by a
    // falsy check on the computed 0).
    expect(screen.getByText('Took 0 s')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/NaN/);
  });
});
