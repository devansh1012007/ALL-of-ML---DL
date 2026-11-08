import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
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

function adminSeed(overrides) {
  return {
    me: { username: 'admin', role: 'admin' },
    admin: {
      users: [
        {
          id: 1,
          username: 'alice',
          role: 'user',
          status: 'active',
          email: null,
          quota_profile_id: 2,
          created_at: '2026-01-01T00:00:00Z',
          last_login_at: null,
          usage: null,
        },
        {
          id: 2,
          username: 'bob',
          role: 'user',
          status: 'pending',
          email: null,
          quota_profile_id: 2,
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
          resets_at: {},
          near_limits: [],
        },
        {
          user_id: 2,
          username: 'bob',
          runs_today: 0,
          queued: 0,
          running: 0,
          storage_bytes: 0,
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
          resets_at: {},
          near_limits: [],
        },
      ],
      profiles: [
        {
          id: 1,
          name: 'free',
          max_concurrent_runs: 1,
          max_queued_runs: 5,
          max_runs_per_day: 20,
          max_run_seconds: 600,
        },
        {
          id: 2,
          name: 'standard',
          max_concurrent_runs: 2,
          max_queued_runs: 20,
          max_runs_per_day: 100,
          max_run_seconds: 3600,
        },
        {
          id: 3,
          name: 'unlimited',
          max_concurrent_runs: null,
          max_queued_runs: null,
          max_runs_per_day: null,
          max_run_seconds: null,
        },
      ],
      queue: [
        {
          id: 101,
          owner: 'alice',
          model_name: 'Random_Forest',
          status: 'running',
          created_at: '2026-11-08T00:00:00Z',
          started_at: '2026-11-08T00:00:00Z',
        },
      ],
      invites: [],
      audit: [],
      ...(overrides || {}),
    },
  };
}

describe('admin mutations: approve pending account', () => {
  it('approving a pending account succeeds and reloads the list', async () => {
    const app = renderApp({ hash: '#/admin', token: 'admin', seed: adminSeed() });
    backend = app.backend;

    await screen.findByText('bob');
    expect(screen.getByText('pending')).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('Approve the pending account'));

    await waitFor(() => {
      expect(backend.state.admin.users.find((u) => u.username === 'bob').status).toBe('active');
    });
    await waitFor(() => {
      // No failure alert, list still rendered, status refreshed to active.
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      expect(screen.getByText('bob')).toBeInTheDocument();
      expect(screen.queryByText('pending')).not.toBeInTheDocument();
    });
    expect(backend.calls.some((c) => c.method === 'POST' && c.pathname === '/api/v1/admin/users/2/approve')).toBe(true);
  });

  it('refused action shows the server reason and the list stays', async () => {
    const app = renderApp({ hash: '#/admin', token: 'admin', seed: adminSeed() });
    backend = app.backend;

    await screen.findByText('bob');
    backend.state.fail['/api/v1/admin/users/2/approve'] = {
      status: 409,
      detail: 'Server refused the approval',
    };

    fireEvent.click(screen.getByTitle('Approve the pending account'));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Server refused the approval');
    expect(screen.getByText('bob')).toBeInTheDocument();
    expect(screen.getByText('alice')).toBeInTheDocument();
    expect(screen.getByText('pending')).toBeInTheDocument();
  });
});

describe('admin mutations: quota save', () => {
  it('saving a user quota succeeds', async () => {
    const app = renderApp({ hash: '#/admin', token: 'admin', seed: adminSeed() });
    backend = app.backend;

    await screen.findByText('alice');
    fireEvent.click(screen.getAllByTitle('Edit the quota of this user')[0]);
    fireEvent.click(await screen.findByText('Save'));

    expect(await screen.findByText('Saved. The limits apply to the next request.')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(backend.calls.some((c) => c.method === 'PATCH' && c.pathname === '/api/v1/admin/users/1')).toBe(true);
  });

  it('refused quota save shows the server reason', async () => {
    const app = renderApp({ hash: '#/admin', token: 'admin', seed: adminSeed() });
    backend = app.backend;

    await screen.findByText('alice');
    fireEvent.click(screen.getAllByTitle('Edit the quota of this user')[0]);
    await screen.findByText('Save');
    backend.state.fail['/api/v1/admin/users/1'] = {
      status: 409,
      detail: 'Server refused the quota save',
    };

    fireEvent.click(screen.getAllByText('Save')[0]);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Server refused the quota save');
    expect(screen.getByText('alice')).toBeInTheDocument();
  });
});

describe('admin mutations: quota profile save', () => {
  it('saving a quota profile succeeds', async () => {
    const app = renderApp({ hash: '#/admin', token: 'admin', seed: adminSeed() });
    backend = app.backend;

    await screen.findByRole('heading', { name: /^admin$/i });
    fireEvent.click(screen.getByRole('button', { name: /quota profiles/i }));

    fireEvent.click((await screen.findAllByRole('button', { name: /^save$/i }))[0]);

    expect(await screen.findByText("The profile 'free' was saved.")).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(backend.calls.some((c) => c.method === 'PUT' && c.pathname === '/api/v1/admin/quota-profiles/1')).toBe(true);
  });

  it('refused profile save shows the server reason', async () => {
    const app = renderApp({ hash: '#/admin', token: 'admin', seed: adminSeed() });
    backend = app.backend;

    await screen.findByRole('heading', { name: /^admin$/i });
    fireEvent.click(screen.getByRole('button', { name: /quota profiles/i }));
    await screen.findAllByRole('button', { name: /^save$/i });
    backend.state.fail['/api/v1/admin/quota-profiles/1'] = {
      status: 409,
      detail: 'Server refused the profile save',
    };

    fireEvent.click(screen.getAllByRole('button', { name: /^save$/i })[0]);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Server refused the profile save');
  });
});

describe('admin mutations: queue cancel', () => {
  it('refused queue cancel shows the server reason', async () => {
    const app = renderApp({ hash: '#/admin', token: 'admin', seed: adminSeed() });
    backend = app.backend;

    await screen.findByRole('heading', { name: /^admin$/i });
    fireEvent.click(screen.getByRole('button', { name: /^queue$/i }));

    await screen.findByText('#101');
    backend.state.fail['/api/v1/admin/queue/101/cancel'] = {
      status: 409,
      detail: 'Server refused the cancel',
    };

    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Server refused the cancel');
    expect(screen.getByText('#101')).toBeInTheDocument();
  });

  it('cancelling a queued run succeeds and reloads the list', async () => {
    const app = renderApp({ hash: '#/admin', token: 'admin', seed: adminSeed() });
    backend = app.backend;

    await screen.findByRole('heading', { name: /^admin$/i });
    fireEvent.click(screen.getByRole('button', { name: /^queue$/i }));

    await screen.findByText('#101');
    const getsBefore = backend.calls.filter(
      (c) => c.method === 'GET' && c.pathname === '/api/v1/admin/queue'
    ).length;

    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));

    await waitFor(() => {
      expect(
        backend.calls.some(
          (c) => c.method === 'POST' && c.pathname === '/api/v1/admin/queue/101/cancel'
        )
      ).toBe(true);
    });
    // The fake backend removes the cancelled run, so a successful cancel
    // followed by the explicit reload must render the empty queue.
    await waitFor(() => {
      expect(screen.getByText('The queue is empty.')).toBeInTheDocument();
    });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByText('#101')).not.toBeInTheDocument();
    expect(
      backend.calls.filter(
        (c) => c.method === 'GET' && c.pathname === '/api/v1/admin/queue'
      ).length
    ).toBeGreaterThan(getsBefore);
  });

  it('refused queue cancel survives a poll tick', async () => {
    const app = renderApp({ hash: '#/admin', token: 'admin', seed: adminSeed() });
    backend = app.backend;

    await screen.findByRole('heading', { name: /^admin$/i });
    fireEvent.click(screen.getByRole('button', { name: /^queue$/i }));

    await screen.findByText('#101');
    backend.state.fail['/api/v1/admin/queue/101/cancel'] = {
      status: 409,
      detail: 'Server refused the cancel',
    };

    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Server refused the cancel');

    const getsBeforePoll = backend.calls.filter(
      (c) => c.method === 'GET' && c.pathname === '/api/v1/admin/queue'
    ).length;

    // The queue polls every 5s on real timers. Wait for at least one poll
    // GET after the refusal, then let its state update settle.
    await waitFor(
      () => {
        expect(
          backend.calls.filter(
            (c) => c.method === 'GET' && c.pathname === '/api/v1/admin/queue'
          ).length
        ).toBeGreaterThan(getsBeforePoll);
      },
      { timeout: 10000 }
    );
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 500));
    });

    expect(screen.getByRole('alert')).toHaveTextContent('Server refused the cancel');
    expect(screen.getByText('#101')).toBeInTheDocument();
  }, 20000);
});

describe('admin mutations: invite create', () => {
  it('creating an invite shows the new code once', async () => {
    const app = renderApp({ hash: '#/admin', token: 'admin', seed: adminSeed() });
    backend = app.backend;

    await screen.findByRole('heading', { name: /^admin$/i });
    fireEvent.click(screen.getByRole('button', { name: /^invites$/i }));

    fireEvent.click(await screen.findByText('Create an invite code'));

    expect(await screen.findByText('CODE-1')).toBeInTheDocument();
    expect(screen.getByText('Copy it now - it is not shown again.')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('refused invite create shows the server reason', async () => {
    const app = renderApp({ hash: '#/admin', token: 'admin', seed: adminSeed() });
    backend = app.backend;

    await screen.findByRole('heading', { name: /^admin$/i });
    fireEvent.click(screen.getByRole('button', { name: /^invites$/i }));
    await screen.findByText('Create an invite code');
    backend.state.fail['/api/v1/admin/invites'] = {
      status: 409,
      detail: 'Server refused the invite',
    };

    fireEvent.click(screen.getByText('Create an invite code'));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Server refused the invite');
    expect(screen.queryByText('CODE-1')).not.toBeInTheDocument();
  });
});

describe('admin reads: usage', () => {
  it('failed usage lookup shows unknown, not zero', async () => {
    const app = renderApp({
      hash: '#/admin',
      token: 'admin',
      seed: {
        ...adminSeed(),
        fail: { '/api/v1/admin/users/1': { status: 500, detail: 'Usage unavailable' } },
      },
    });
    backend = app.backend;

    await screen.findByText('alice');
    expect(await screen.findByText('Usage could not be loaded.')).toBeInTheDocument();
    // Unknowns present, no zero usage figures for alice's row.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    const aliceRow = screen.getByText('alice').closest('tr');
    expect(aliceRow.textContent).not.toContain('0 / 20');
    expect(aliceRow.textContent).not.toContain('0 B');
    expect(aliceRow.textContent).toContain('— / ∞');
  });

  it('true zero usage still shows zero', async () => {
    const app = renderApp({ hash: '#/admin', token: 'admin', seed: adminSeed() });
    backend = app.backend;

    await screen.findByText('alice');
    await waitFor(() => {
      expect(document.body.textContent).toContain('0 / 20');
    });
    expect(document.body.textContent).toContain('0 B');
  });
});

describe('admin reads: quota profiles', () => {
  it('failed quota profile lookup shows unknown, not free', async () => {
    const app = renderApp({
      hash: '#/admin',
      token: 'admin',
      seed: {
        ...adminSeed(),
        fail: { '/api/v1/admin/quota-profiles': { status: 500, detail: 'Profiles unavailable' } },
      },
    });
    backend = app.backend;

    await screen.findByText('alice');
    expect(await screen.findByText('Quota profiles could not be loaded.')).toBeInTheDocument();
    // alice and bob both have quota_profile_id 2 (standard); without profiles
    // the cell must read unknown, never the invented free fallback.
    const rows = screen.getAllByText('—');
    expect(rows.length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toContain('free');
  });

  it('loaded quota profile shows the true name', async () => {
    const app = renderApp({ hash: '#/admin', token: 'admin', seed: adminSeed() });
    backend = app.backend;

    await screen.findByText('alice');
    await waitFor(() => {
      expect(screen.getAllByText('standard').length).toBeGreaterThan(0);
    });
  });
});

describe('admin design: R4 shared classes', () => {
  it('marks the active tab with aria-current', async () => {
    const app = renderApp({ hash: '#/admin', token: 'admin', seed: adminSeed() });
    backend = app.backend;

    await screen.findByRole('heading', { name: /^admin$/i });
    expect(screen.getByRole('button', { name: /^users$/i })).toHaveAttribute('aria-current', 'page');

    fireEvent.click(screen.getByRole('button', { name: /^queue$/i }));

    await screen.findByText('#101');
    expect(screen.getByRole('button', { name: /^queue$/i })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: /^users$/i })).not.toHaveAttribute('aria-current');
  });

  it('uses shared field/btn/th/td classes for tables, quota editor and saves', async () => {
    const app = renderApp({ hash: '#/admin', token: 'admin', seed: adminSeed() });
    backend = app.backend;

    await screen.findByText('alice');
    // Users table headers/cells use the shared .th/.td classes.
    const headers = document.querySelectorAll('th');
    expect(headers.length).toBeGreaterThan(0);
    headers.forEach((th) => expect(th.classList.contains('th')).toBe(true));
    expect(document.querySelector('.admin-table-wrap')).not.toBeNull();

    fireEvent.click(screen.getAllByTitle('Edit the quota of this user')[0]);

    const saveBtn = await screen.findByText('Save');
    expect(saveBtn.classList.contains('btn')).toBe(true);
    expect(saveBtn.classList.contains('btn-primary')).toBe(true);

    const select = document.querySelector('select');
    expect(select).not.toBeNull();
    expect(select.classList.contains('field')).toBe(true);

    const numberInputs = document.querySelectorAll('input[type="number"]');
    expect(numberInputs.length).toBeGreaterThan(0);
    numberInputs.forEach((input) => expect(input.classList.contains('field')).toBe(true));

    // Icon actions keep their titles and use the shared icon button class.
    expect(screen.getByTitle('Approve the pending account').classList.contains('admin-icon-btn')).toBe(true);
  });
});
