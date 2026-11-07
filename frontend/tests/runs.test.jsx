import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { screen, cleanup, act } from '@testing-library/react';
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
