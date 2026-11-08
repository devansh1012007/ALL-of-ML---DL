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

describe('smoke: auth gate', () => {
  it('renders the sign-in form when no token is stored', async () => {
    const app = renderApp({});
    backend = app.backend;

    expect(await screen.findByRole('heading', { name: /^sign in$/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/^username$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^sign in$/i })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /^models$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /^admin$/i })).not.toBeInTheDocument();
  });
});

describe('smoke: authenticated app', () => {
  it('renders the models catalog and admin nav for an admin', async () => {
    const app = renderApp({
      hash: '#/models',
      token: 'admin',
      seed: {
        me: { username: 'admin', role: 'admin' },
        models: [
          {
            name: 'Fake_Forest',
            category: 'classification',
            description: 'A fake model for tests.',
            parameters: {},
            optimization: [],
            test_results: null,
          },
        ],
      },
    });
    backend = app.backend;

    expect(await screen.findByRole('heading', { name: /^models$/i })).toBeInTheDocument();
    expect(await screen.findByText('Fake_Forest')).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: /^admin$/i })).toBeInTheDocument();
    expect(screen.getByText('admin')).toBeInTheDocument();

    expect(backend.calls.some((c) => c.pathname === '/api/v1/me')).toBe(true);
    expect(backend.calls.some((c) => c.pathname === '/api/v1/ml/models')).toBe(true);
  });
});

describe('smoke: run details cancel', () => {
  it('shows the backend note when cancelling a running run', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: {
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
            status: 'running',
            job_kind: 'train',
            artifact_path: null,
            artifact_removed: false,
            metrics: null,
            tags: [],
            note: null,
            created_at: '2026-11-08T00:00:00Z',
            updated_at: '2026-11-08T00:00:00Z',
            started_at: '2026-11-08T00:00:00Z',
            finished_at: null,
            wall_seconds: null,
          },
        ],
      },
    });
    backend = app.backend;

    const cancelButton = await screen.findByRole('button', { name: /^cancel run$/i });
    fireEvent.click(cancelButton);

    expect(
      await screen.findByText(/The training cannot be interrupted once it started/i)
    ).toBeInTheDocument();
    expect(
      backend.calls.some(
        (c) => c.method === 'POST' && c.pathname === '/api/v1/ml/runs/1/cancel'
      )
    ).toBe(true);
  });
});

describe('smoke: admin screen', () => {
  it('renders the admin screen from mocked admin responses', async () => {
    const app = renderApp({
      hash: '#/admin',
      token: 'admin',
      seed: {
        me: { username: 'admin', role: 'admin' },
        admin: {
          users: [
            {
              id: 1,
              username: 'alice',
              role: 'user',
              status: 'active',
              email: null,
              quota_profile_id: null,
              created_at: '2026-01-01T00:00:00Z',
              last_login_at: null,
              usage: null,
            },
          ],
          usage: [
            {
              user_id: 1,
              username: 'alice',
              runs_today: 0,
              queued: 0,
              running: 0,
              storage_bytes: 2048,
              datasets: 1,
              cpu_seconds_this_month: 0,
              limits: {
                max_runs_per_day: 20,
                max_queued_runs: 5,
                max_concurrent_runs: 1,
                max_storage_bytes: 500 * 1024 * 1024,
                max_datasets: 10,
                max_cpu_seconds_per_month: 7200,
              },
              resets_at: {
                max_runs_per_day: '2026-11-09T00:00:00Z',
                max_cpu_seconds_per_month: '2026-12-01T00:00:00Z',
              },
              near_limits: [],
            },
          ],
          queue: [],
          invites: [],
          audit: [],
        },
      },
    });
    backend = app.backend;

    expect(await screen.findByRole('heading', { name: /^admin$/i })).toBeInTheDocument();
    expect(await screen.findByText('alice')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^users$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^queue$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /quota profiles/i })).toBeInTheDocument();

    expect(
      backend.calls.some((c) => c.pathname === '/api/v1/admin/users')
    ).toBe(true);
    expect(
      backend.calls.some((c) => c.pathname === '/api/v1/admin/usage')
    ).toBe(true);
    expect(
      backend.calls.some((c) => c.pathname === '/api/v1/admin/quota-profiles')
    ).toBe(true);
  });
});
