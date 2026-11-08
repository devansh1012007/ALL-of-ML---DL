import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { screen, cleanup, fireEvent } from '@testing-library/react';
import { renderApp, teardownApp } from './helpers.jsx';
import {
  resolveTheme,
  applyTheme,
  toggleTheme,
  THEME_STORAGE_KEY,
} from '../components/theme.jsx';

// T-101 theme tests: resolution order, hostile values, storage-throw
// fallback, toggle side effects. All storage/DOM state is cleaned in
// afterEach (helpers teardown only removes prime_token).

let backend;

function stubMatchMedia(matches) {
  const fn = (query) => ({
    matches: query === '(prefers-color-scheme: light)' ? matches : false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  });
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: fn,
  });
  return fn;
}

function ensureMeta() {
  let meta = document.querySelector('meta[name="color-scheme"]');
  if (!meta) {
    meta = document.createElement('meta');
    meta.setAttribute('name', 'color-scheme');
    document.head.appendChild(meta);
  }
  meta.setAttribute('content', 'dark');
}

function getMetaContent() {
  return document.querySelector('meta[name="color-scheme"]')?.getAttribute('content');
}

// jsdom's Storage getItem/setItem are not shadowable via vi.spyOn (prototype
// methods, assignment silently ignored — verified by forcing the seams), so
// throw stubs replace the whole global Storage with a thin wrapper that
// delegates except for the one key that must throw.
function stubThrowingStorage({ getThrowsFor = null, setThrowsFor = null } = {}) {
  const original = window.localStorage;
  const throwing = {
    getItem: (key) => {
      if (key === getThrowsFor) throw new Error('storage denied');
      return original.getItem(key);
    },
    setItem: (key, value) => {
      if (key === setThrowsFor) throw new Error('storage denied');
      return original.setItem(key, value);
    },
    removeItem: (key) => original.removeItem(key),
    clear: () => original.clear(),
  };
  vi.stubGlobal('localStorage', throwing);
}

beforeEach(() => {
  vi.useRealTimers();
  window.localStorage.clear();
  window.location.hash = '';
  delete document.documentElement.dataset.theme;
  ensureMeta();
});

afterEach(() => {
  teardownApp(backend);
  backend = undefined;
  window.localStorage.removeItem('prime_token');
  window.localStorage.removeItem('prime_theme');
  delete document.documentElement.dataset.theme;
  window.location.hash = '';
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  delete window.matchMedia;
});

describe('theme: resolution order', () => {
  it('stored light beats system dark', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    stubMatchMedia(false);
    expect(resolveTheme()).toBe('light');
  });

  it('stored dark beats system light', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    stubMatchMedia(true);
    expect(resolveTheme()).toBe('dark');
  });

  it('absent + system light resolves light', () => {
    stubMatchMedia(true);
    expect(resolveTheme()).toBe('light');
  });

  it('absent + system dark resolves dark', () => {
    stubMatchMedia(false);
    expect(resolveTheme()).toBe('dark');
  });

  it('absent + matchMedia absent (jsdom default) resolves dark', () => {
    delete window.matchMedia;
    expect(typeof window.matchMedia).not.toBe('function');
    expect(resolveTheme()).toBe('dark');
  });

  it('App mount applies stored light to attribute + meta', async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    stubMatchMedia(false);
    const app = renderApp({ token: 'testuser' });
    backend = app.backend;
    // App state reconciles from storage on mount and applies through the
    // single applyTheme path.
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(getMetaContent()).toBe('light');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
    // Light is active, so the toggle offers the dark action and is pressed.
    const toggle = screen.getByRole('button', { name: /switch to (light|dark) mode/i });
    expect(toggle).toHaveTextContent('Switch to dark mode');
    expect(toggle.getAttribute('aria-pressed')).toBe('true');
  });
});

describe('theme: hostile stored values fall through', () => {
  const hostiles = [
    ['xss', '"><script>alert(1)</script>'],
    ['10KB', 'a'.repeat(10240)],
    ['unicode-only', '🙂🚀✨'.repeat(64)],
    ['empty string', ''],
    ['uppercase LIGHT', 'LIGHT'],
  ];

  for (const [name, value] of hostiles) {
    it(`hostile ${name} resolves to default with no script created`, () => {
      window.localStorage.setItem(THEME_STORAGE_KEY, value);
      stubMatchMedia(false);
      const beforeScripts = document.querySelectorAll('script').length;
      expect(resolveTheme()).toBe('dark');
      // The resolved token — never the raw string — is the only thing that
      // may reach dataset.theme; no element/script is created from it.
      applyTheme(resolveTheme());
      expect(document.documentElement.dataset.theme).toBe('dark');
      expect(document.documentElement.dataset.theme).not.toBe(value);
      expect(document.querySelectorAll('script').length).toBe(beforeScripts);
      expect(document.querySelector('script[data-hostile]')).toBeNull();
    });
  }

  it('hostile value still allows toggle to work', async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, '"><script>alert(1)</script>');
    stubMatchMedia(false);
    const app = renderApp({ token: 'testuser' });
    backend = app.backend;
    // Hostile is ignored on mount; default dark is applied.
    expect(document.documentElement.dataset.theme).toBe('dark');
    const toggle = screen.getByRole('button', { name: /switch to (light|dark) mode/i });
    fireEvent.click(toggle);
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
    expect(document.querySelectorAll('script').length).toBe(0);
  });
});

describe('theme: localStorage throw fallback', () => {
  it('resolveTheme returns dark when the storage read throws', () => {
    stubMatchMedia(true);
    stubThrowingStorage({ getThrowsFor: THEME_STORAGE_KEY });
    expect(() => resolveTheme()).not.toThrow();
    expect(resolveTheme()).toBe('dark');
  });

  it('applyTheme flips attribute + meta in-memory when the storage write throws', () => {
    stubThrowingStorage({ setThrowsFor: THEME_STORAGE_KEY });
    expect(() => applyTheme('light')).not.toThrow();
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(getMetaContent()).toBe('light');
  });

  it('toggle flips in-memory when setItem throws for prime_theme', async () => {
    const app = renderApp({ token: 'testuser' });
    backend = app.backend;
    stubThrowingStorage({ setThrowsFor: THEME_STORAGE_KEY });
    const toggle = screen.getByRole('button', { name: /switch to (light|dark) mode/i });
    expect(() => fireEvent.click(toggle)).not.toThrow();
    // In-memory flip survives the denied write until reload.
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(getMetaContent()).toBe('light');
  });
});

describe('theme: toggle side effects', () => {
  it('header toggle flips attribute + meta + storage in one click (authenticated)', async () => {
    const app = renderApp({ token: 'testuser' });
    backend = app.backend;
    // Dark is the default at rest.
    expect(document.documentElement.dataset.theme).toBe('dark');
    const toggle = screen.getByRole('button', { name: /switch to (light|dark) mode/i });
    expect(toggle).toHaveTextContent('Switch to light mode');
    expect(toggle.getAttribute('aria-pressed')).toBe('false');
    // The toggle lives outside <nav> (smoke tests query nav by role/name).
    expect(document.querySelector('nav')?.contains(toggle)).toBe(false);
    fireEvent.click(toggle);
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(getMetaContent()).toBe('light');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
    // Label describes the next action, not the current state.
    const flipped = screen.getByRole('button', { name: /switch to (light|dark) mode/i });
    expect(flipped).toHaveTextContent('Switch to dark mode');
    expect(flipped.getAttribute('aria-pressed')).toBe('true');
    // Second click flips back.
    fireEvent.click(flipped);
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(getMetaContent()).toBe('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
  });

  it('sign-in card renders the same toggle and persists across the gate', async () => {
    const app = renderApp({});
    backend = app.backend;
    const toggle = screen.getByRole('button', { name: /switch to (light|dark) mode/i });
    expect(toggle).toHaveTextContent('Switch to light mode');
    fireEvent.click(toggle);
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
    // Reload simulation: fresh App mount with the same storage keeps light.
    teardownApp(backend);
    backend = undefined;
    delete document.documentElement.dataset.theme;
    ensureMeta();
    const remounted = renderApp({});
    backend = remounted.backend;
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(getMetaContent()).toBe('light');
  });

  it('sign-out does NOT clear prime_theme', async () => {
    const app = renderApp({ token: 'testuser' });
    backend = app.backend;
    const toggle = screen.getByRole('button', { name: /switch to (light|dark) mode/i });
    fireEvent.click(toggle);
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
    fireEvent.click(screen.getByRole('button', { name: /^sign out$/i }));
    // Sign-in view returns, but the per-browser preference survives logout.
    expect(await screen.findByRole('heading', { name: /^sign in$/i })).toBeInTheDocument();
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
    expect(document.documentElement.dataset.theme).toBe('light');
    const authToggle = screen.getByRole('button', { name: /switch to (light|dark) mode/i });
    expect(authToggle).toHaveTextContent('Switch to dark mode');
    expect(authToggle.getAttribute('aria-pressed')).toBe('true');
  });

  it('toggleTheme is a pure flip', () => {
    expect(toggleTheme('dark')).toBe('light');
    expect(toggleTheme('light')).toBe('dark');
    document.documentElement.dataset.theme = 'light';
    expect(toggleTheme()).toBe('dark');
  });
});
