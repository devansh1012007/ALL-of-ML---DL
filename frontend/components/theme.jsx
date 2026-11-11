// T-101 light mode: single theme helper + toggle button.
// Invariant: every write (dataset.theme + meta color-scheme + prime_theme)
// goes through applyTheme() — no split-brain between React state and the DOM.
// The stored value is allow-listed ("light"/"dark") and never reaches
// HTML parsing — resolveTheme() returns a resolved token, never the raw string.
import React from 'react';

export const THEME_STORAGE_KEY = 'prime_theme';

export function resolveTheme() {
  let stored;
  try {
    // SECURITY: access itself can throw (sandbox/private mode) — fall through
    // to dark, never an uncaught exception out of a render path.
    stored = localStorage.getItem(THEME_STORAGE_KEY);
  } catch {
    return 'dark';
  }
  if (stored === 'light' || stored === 'dark') {
    return stored;
  }
  if (typeof window.matchMedia === 'function') {
    try {
      if (window.matchMedia('(prefers-color-scheme: light)').matches) {
        return 'light';
      }
    } catch {
      return 'dark';
    }
  }
  return 'dark';
}

export function applyTheme(theme) {
  // INVARIANT: only the two allow-listed tokens ever touch the DOM.
  const next = theme === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  let meta = document.querySelector('meta[name="color-scheme"]');
  if (!meta) {
    meta = document.createElement('meta');
    meta.setAttribute('name', 'color-scheme');
    document.head.appendChild(meta);
  }
  meta.setAttribute('content', next);
  try {
    // SECURITY: write throw (denied storage) still leaves the in-memory
    // flip above — the preference survives until reload, never crashes.
    localStorage.setItem(THEME_STORAGE_KEY, next);
  } catch {
    // Storage denied — in-memory theme already applied.
  }
  return next;
}

export function toggleTheme(current) {
  // Pure flip: the caller applies through applyTheme() (single writer path).
  const cur =
    typeof current === 'string'
      ? current
      : document.documentElement.dataset.theme;
  return cur === 'light' ? 'dark' : 'light';
}

export function ThemeToggle({ theme, onToggle }) {
  const isLight = theme === 'light';
  const label = isLight ? 'Switch to dark mode' : 'Switch to light mode';
  return (
    <button
      type="button"
      aria-pressed={isLight}
      onClick={onToggle}
      className="btn btn-quiet"
    >
      {label}
    </button>
  );
}
