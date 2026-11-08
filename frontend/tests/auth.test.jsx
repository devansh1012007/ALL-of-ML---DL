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
