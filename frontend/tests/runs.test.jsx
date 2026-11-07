import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { screen, cleanup, act, waitFor } from '@testing-library/react';
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
