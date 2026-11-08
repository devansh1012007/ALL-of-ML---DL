import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { screen, cleanup, within } from '@testing-library/react';
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

function completedWithMetrics(id, modelName, accuracy) {
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
