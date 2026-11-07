import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { screen, cleanup, fireEvent } from '@testing-library/react';
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

function completedPredictSeed(extraFail) {
  return {
    runs: [
      {
        id: 1,
        model_name: 'Random_Forest',
        dataset_source: 'local',
        dataset_tag: 'sample.csv',
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
      },
    ],
    runDetails: {
      1: {
        id: 1,
        model_name: 'Random_Forest',
        dataset_source: 'local',
        dataset_tag: 'sample.csv',
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
          accuracy: 0.9,
          baseline_accuracy: 0.5,
          artifact_kind: 'tabular',
        },
        tags: [],
        note: null,
        created_at: '2026-11-08T00:00:00Z',
        updated_at: '2026-11-08T00:00:00Z',
        started_at: '2026-11-08T00:00:00Z',
        finished_at: '2026-11-08T00:01:00Z',
        wall_seconds: 60,
      },
    },
    ...(extraFail ? { fail: extraFail } : {}),
  };
}

describe('predict: invalid JSON input shows friendly message', () => {
  it('bad JSON shows rows-must-be-JSON message, not "Unexpected token"', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: completedPredictSeed(),
    });
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /^use this model$/i })
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: /several rows/i })
    );
    const textarea = await screen.findByLabelText(/rows as json/i);
    fireEvent.change(textarea, { target: { value: 'not-json' } });
    fireEvent.click(screen.getByRole('button', { name: /^predict$/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      /Rows must be valid JSON\. Check the input and try again\./
    );
    expect(alert).not.toHaveTextContent(/Unexpected token/);
  });
});

describe('predict: server error shown verbatim, distinct from input error', () => {
  it('server predict reject still shows the server message', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: completedPredictSeed({
        '/api/v1/ml/runs/1/predict': {
          status: 400,
          detail: 'Server refused the prediction',
        },
      }),
    });
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /^use this model$/i })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^predict$/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Server refused the prediction');
    expect(alert).not.toHaveTextContent(/Rows must be valid JSON/);
  });
});
