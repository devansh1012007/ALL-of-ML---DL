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

async function submitLogin() {
  fireEvent.change(screen.getByLabelText(/^username$/i), {
    target: { value: 'testuser' },
  });
  fireEvent.change(screen.getByLabelText(/^password$/i), {
    target: { value: 'secret123' },
  });
  fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }));
}

describe('auth: network failure shows friendly message', () => {
  it('login network reject shows connectivity sentence, not "Failed to fetch"', async () => {
    const app = renderApp({
      seed: {
        fail: {
          '/token': { network: true, message: 'Failed to fetch' },
        },
      },
    });
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /^sign in$/i })
    ).toBeInTheDocument();
    await submitLogin();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      /Could not reach the server\. Check your connection and try again\./
    );
    expect(alert).not.toHaveTextContent(/Failed to fetch/);
    expect(alert).not.toHaveTextContent(/TypeError/);
  });

  it('login HTTP error without JSON detail shows connectivity sentence, not "HTTP error! status"', async () => {
    const app = renderApp({});
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /^sign in$/i })
    ).toBeInTheDocument();

    // Simulate an HTML/plaintext error page: response.json() throws, so
    // apiFetch has no JSON detail to show. The harness always returns JSON
    // for `fail`, so wrap fetch here for this one case.
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
      if (pathname === '/token') {
        return {
          ok: false,
          status: 502,
          json: async () => {
            throw new SyntaxError('Unexpected token < in JSON at position 0');
          },
          text: async () => '<html><body>Bad Gateway</body></html>',
          blob: async () => new Blob(['Bad Gateway']),
        };
      }
      return fakeFetch(input, options);
    };

    await submitLogin();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      /Could not reach the server\. Check your connection and try again\./
    );
    expect(alert).not.toHaveTextContent(/HTTP error! status/);
  });
});

describe('auth: 401 preserves logout and session-expired', () => {
  it('a 401 from /me logs out and shows the session-expired notice', async () => {
    const app = renderApp({
      token: 'testuser',
      seed: {
        fail: {
          '/api/v1/me': { status: 401, detail: 'Unauthorized' },
        },
      },
    });
    backend = app.backend;

    // App must drop back to the sign-in view with the session notice.
    expect(
      await screen.findByRole('heading', { name: /^sign in$/i })
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/Session expired\. Please log in again\./)
    ).toBeInTheDocument();
    expect(window.localStorage.getItem('prime_token')).toBeNull();
  });
});

describe('auth: R3a sign-in card + successful submit', () => {
  it('sign-in form sits in the shared auth card and labels keep autocomplete', async () => {
    const app = renderApp({});
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /^sign in$/i })
    ).toBeInTheDocument();

    // R3a shared card wrapper (absent before the redesign).
    const card = document.querySelector('.auth-card');
    expect(card).not.toBeNull();
    expect(card).toContainElement(screen.getByLabelText(/^username$/i));
    expect(card).toContainElement(screen.getByLabelText(/^password$/i));

    // Unchanged labelling contract: htmlFor ids plus autocomplete hints.
    expect(screen.getByLabelText(/^username$/i)).toHaveAttribute('autocomplete', 'username');
    expect(screen.getByLabelText(/^password$/i)).toHaveAttribute('autocomplete', 'current-password');
  });

  it('successful submit stores the token and leaves the sign-in view', async () => {
    const app = renderApp({});
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /^sign in$/i })
    ).toBeInTheDocument();
    await submitLogin();

    // After login the app shell renders with the Runs heading and no alert.
    expect(
      await screen.findByRole('heading', { name: /^runs$/i })
    ).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(window.localStorage.getItem('prime_token')).not.toBeNull();
  });

  it('register mode keeps the create-account wording and mode toggle', async () => {
    const app = renderApp({});
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /^sign in$/i })
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /create an account/i }));

    expect(
      await screen.findByRole('heading', { name: /create an account/i })
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toHaveAttribute('autocomplete', 'new-password');
    expect(screen.getByText('At least 8 characters.')).toBeInTheDocument();
  });
});

describe('auth: T-304 failed submission exposes aria-invalid + aria-describedby on the fields', () => {
  it('fields carry no invalid state before a failed submission', async () => {
    const app = renderApp({});
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /^sign in$/i })
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/^username$/i)).not.toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText(/^password$/i)).not.toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText(/^username$/i)).not.toHaveAttribute('aria-describedby');
    expect(screen.getByLabelText(/^password$/i)).not.toHaveAttribute('aria-describedby');
    // Guard self-check: a bare input without the attrs fails the pins below.
    const bare = document.createElement('input');
    expect(bare.getAttribute('aria-invalid')).toBeNull();
  });

  // INVARIANT: every present aria-describedby resolves to the alert element.
  function checkDescribedByInvariant(alert) {
    const described = document.querySelectorAll('[aria-describedby]');
    for (const el of described) {
      const target = document.getElementById(el.getAttribute('aria-describedby'));
      expect(target, `aria-describedby on ${el.id || el.tagName} resolves`).toBe(alert);
    }
  }

  it('network failure marks neither field invalid but describes both with the alert text', async () => {
    const app = renderApp({
      seed: {
        fail: {
          '/token': { network: true, message: 'Failed to fetch' },
        },
      },
    });
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /^sign in$/i })
    ).toBeInTheDocument();
    await submitLogin();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/Could not reach the server/);
    const describedBy = alert.getAttribute('id');
    expect(describedBy, 'alert carries an id for aria-describedby').toBeTruthy();

    const username = screen.getByLabelText(/^username$/i);
    const password = screen.getByLabelText(/^password$/i);
    for (const field of [username, password]) {
      expect(field).not.toHaveAttribute('aria-invalid');
      expect(field).toHaveAttribute('aria-describedby', describedBy);
    }
    checkDescribedByInvariant(alert);
    // Mutation tripwire: old both-fields code marks invalid -> fails not.toHaveAttribute.
  });

  it('register 409 marks username-only invalid (password-negative absent)', async () => {
    const app = renderApp({
      seed: {
        fail: {
          '/api/v1/register': { status: 409, detail: 'Username taken' },
        },
      },
    });
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /^sign in$/i })
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /create an account/i }));
    expect(
      await screen.findByRole('heading', { name: /create an account/i })
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^username$/i), {
      target: { value: 'testuser' },
    });
    fireEvent.change(screen.getByLabelText(/^password$/i), {
      target: { value: 'secret123' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^create account$/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/already taken/);
    const alertId = alert.getAttribute('id');
    expect(alertId).toBeTruthy();

    const username = screen.getByLabelText(/^username$/i);
    const password = screen.getByLabelText(/^password$/i);
    expect(username).toHaveAttribute('aria-invalid', 'true');
    expect(username).toHaveAttribute('aria-describedby', alertId);
    expect(password).not.toHaveAttribute('aria-invalid');
    expect(password).not.toHaveAttribute('aria-describedby');
    checkDescribedByInvariant(alert);
  });

  it('login 429 describes both but invalidates neither', async () => {
    const app = renderApp({
      seed: { fail: { '/token': { status: 429, detail: 'Rate limited' } } },
    });
    backend = app.backend;
    expect(
      await screen.findByRole('heading', { name: /^sign in$/i })
    ).toBeInTheDocument();
    await submitLogin();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/Too many attempts/);
    const alertId = alert.getAttribute('id');
    for (const field of [screen.getByLabelText(/^username$/i), screen.getByLabelText(/^password$/i)]) {
      expect(field).not.toHaveAttribute('aria-invalid');
      expect(field).toHaveAttribute('aria-describedby', alertId);
    }
    checkDescribedByInvariant(alert);
  });

  it('login 502 server error describes both but invalidates neither', async () => {
    const app = renderApp({
      seed: { fail: { '/token': { status: 502, detail: 'Bad gateway' } } },
    });
    backend = app.backend;
    expect(
      await screen.findByRole('heading', { name: /^sign in$/i })
    ).toBeInTheDocument();
    await submitLogin();
    const alert = await screen.findByRole('alert');
    const alertId = alert.getAttribute('id');
    for (const field of [screen.getByLabelText(/^username$/i), screen.getByLabelText(/^password$/i)]) {
      expect(field).not.toHaveAttribute('aria-invalid');
      expect(field).toHaveAttribute('aria-describedby', alertId);
    }
    checkDescribedByInvariant(alert);
  });

  it('login 500 server error describes both but invalidates neither', async () => {
    const app = renderApp({
      seed: { fail: { '/token': { status: 500, detail: 'Server error' } } },
    });
    backend = app.backend;
    expect(
      await screen.findByRole('heading', { name: /^sign in$/i })
    ).toBeInTheDocument();
    await submitLogin();
    const alert = await screen.findByRole('alert');
    const alertId = alert.getAttribute('id');
    for (const field of [screen.getByLabelText(/^username$/i), screen.getByLabelText(/^password$/i)]) {
      expect(field).not.toHaveAttribute('aria-invalid');
      expect(field).toHaveAttribute('aria-describedby', alertId);
    }
    checkDescribedByInvariant(alert);
  });

  it('login 400 marks both fields invalid and describes both (guard-rail)', async () => {
    const app = renderApp({
      seed: { fail: { '/token': { status: 400, detail: 'Incorrect username or password' } } },
    });
    backend = app.backend;
    expect(
      await screen.findByRole('heading', { name: /^sign in$/i })
    ).toBeInTheDocument();
    await submitLogin();
    const alert = await screen.findByRole('alert');
    const alertId = alert.getAttribute('id');
    for (const field of [screen.getByLabelText(/^username$/i), screen.getByLabelText(/^password$/i)]) {
      expect(field).toHaveAttribute('aria-invalid', 'true');
      expect(field).toHaveAttribute('aria-describedby', alertId);
    }
    checkDescribedByInvariant(alert);
  });

  it('login 403 describes both but invalidates neither (user-confirmed whitelist)', async () => {
    const app = renderApp({
      seed: { fail: { '/token': { status: 403, detail: 'Invite required' } } },
    });
    backend = app.backend;
    expect(
      await screen.findByRole('heading', { name: /^sign in$/i })
    ).toBeInTheDocument();
    await submitLogin();
    const alert = await screen.findByRole('alert');
    const alertId = alert.getAttribute('id');
    for (const field of [screen.getByLabelText(/^username$/i), screen.getByLabelText(/^password$/i)]) {
      expect(field).not.toHaveAttribute('aria-invalid');
      expect(field).toHaveAttribute('aria-describedby', alertId);
    }
    checkDescribedByInvariant(alert);
  });

  it('login 401 defensive describes both but invalidates neither', async () => {
    const app = renderApp({
      seed: { fail: { '/token': { status: 401, detail: 'Unauthorized' } } },
    });
    backend = app.backend;
    expect(
      await screen.findByRole('heading', { name: /^sign in$/i })
    ).toBeInTheDocument();
    await submitLogin();
    const alert = await screen.findByRole('alert');
    const alertId = alert.getAttribute('id');
    for (const field of [screen.getByLabelText(/^username$/i), screen.getByLabelText(/^password$/i)]) {
      expect(field).not.toHaveAttribute('aria-invalid');
      expect(field).toHaveAttribute('aria-describedby', alertId);
    }
    checkDescribedByInvariant(alert);
  });
});
