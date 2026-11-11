import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { screen, cleanup, within, fireEvent, waitFor } from '@testing-library/react';
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

function completedWithMetrics(id, modelName, accuracy, f1) {
  return {
    id,
    model_name: modelName,
    dataset_source: 'local',
    dataset_tag: 'compare.csv',
    dataset_id: 1,
    mode: 'manual',
    env_id: null,
    optimize_metric: 'accuracy',
    model_candidates: null,
    status: 'completed',
    job_kind: 'train',
    artifact_path: 'models/fake.joblib',
    artifact_removed: false,
    metrics: {
      accuracy,
      ...(f1 === undefined ? {} : { f1_macro: f1 }),
      baseline_accuracy: 0.5,
    },
    tags: [],
    note: null,
    created_at: '2026-11-08T00:00:00Z',
    updated_at: '2026-11-08T00:00:00Z',
    started_at: '2026-11-08T00:00:00Z',
    finished_at: '2026-11-08T00:01:00Z',
    wall_seconds: 60,
  };
}

describe('compare: best bar says "best", not colour only', () => {
  it('best run bar in the By metric section has visible "best" text', async () => {
    const app = renderApp({
      hash: '#/compare/1+2',
      token: 'testuser',
      seed: {
        runs: [
          completedWithMetrics(1, 'Top_Forest', 0.9),
          completedWithMetrics(2, 'Low_Tree', 0.7),
        ],
      },
    });
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /by metric/i })
    ).toBeInTheDocument();

    const byMetric = screen
      .getByRole('heading', { name: /by metric/i })
      .closest('section');
    expect(byMetric).not.toBeNull();

    // The bar value itself carries the text cue: "0.900 best".
    expect(within(byMetric).getByText(/0\.900 best/)).toBeInTheDocument();
    // The non-best bar is unchanged (no spurious cue).
    expect(within(byMetric).queryByText(/0\.700 best/)).not.toBeInTheDocument();
    // Exactly one bar cue in this section (the header sentence is outside it,
    // and the table's own "best" lives in a different section).
    expect(within(byMetric).getAllByText(/best/i)).toHaveLength(1);
  });
});

describe('compare: R3b layout, metric switch, and run navigation', () => {
  it('renders the shared R3b layout hooks for page, chart, and table', async () => {
    const app = renderApp({
      hash: '#/compare/1+2',
      token: 'testuser',
      seed: {
        runs: [
          completedWithMetrics(1, 'Top_Forest', 0.9),
          completedWithMetrics(2, 'Low_Tree', 0.7),
        ],
      },
    });
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /compare 2 runs/i })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/the same score side by side/i)
    ).toBeInTheDocument();
    // R3b shared layout hooks (absent before the redesign).
    expect(document.querySelector('.compare-page')).not.toBeNull();
    expect(document.querySelector('.compare-chart')).not.toBeNull();
    expect(document.querySelector('.compare-table-wrap')).not.toBeNull();
    // Both runs are charted and tabulated.
    expect(screen.getByText('#1 Top_Forest')).toBeInTheDocument();
    expect(screen.getByText('#2 Low_Tree')).toBeInTheDocument();
    expect(screen.getAllByRole('columnheader', { name: /top_forest/i })).toHaveLength(1);
    expect(screen.getAllByRole('columnheader', { name: /low_tree/i })).toHaveLength(1);
    // The table keeps its own best cue, separate from the chart bar cue.
    const tableWrap = document.querySelector('.compare-table-wrap');
    expect(within(tableWrap).getByText('best')).toBeInTheDocument();
  });

  it('switching the chart metric re-ranks the bars and keeps the best cue', async () => {
    const app = renderApp({
      hash: '#/compare/1+2',
      token: 'testuser',
      seed: {
        runs: [
          completedWithMetrics(1, 'Top_Forest', 0.9, 0.72),
          completedWithMetrics(2, 'Low_Tree', 0.7, 0.88),
        ],
      },
    });
    backend = app.backend;

    const byMetric = await screen.findByRole('heading', {
      name: /by metric/i,
    });
    const section = byMetric.closest('section');
    // Accuracy: run 1 is best.
    expect(within(section).getByText(/0\.900 best/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/metric/i), {
      target: { value: 'f1_macro' },
    });

    await waitFor(() => {
      expect(within(section).getByText(/0\.880 best/)).toBeInTheDocument();
    });
    expect(within(section).queryByText(/0\.720 best/)).not.toBeInTheDocument();
    expect(within(section).getAllByText(/best/i)).toHaveLength(1);
    expect(within(section).getByText('Higher is better.')).toBeInTheDocument();
  });

  it('clicking a run name in the table navigates to its details view', async () => {
    const app = renderApp({
      hash: '#/compare/1+2',
      token: 'testuser',
      seed: {
        runs: [
          completedWithMetrics(1, 'Top_Forest', 0.9),
          completedWithMetrics(2, 'Low_Tree', 0.7),
        ],
      },
    });
    backend = app.backend;

    await screen.findByRole('heading', { name: /compare 2 runs/i });
    const link = document.querySelector('.compare-run-link');
    expect(link).not.toBeNull();
    expect(link).toHaveTextContent('Top_Forest');
    fireEvent.click(link);
    expect(window.location.hash).toBe('#/run-details/1');
  });
});
