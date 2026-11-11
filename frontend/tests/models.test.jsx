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

describe('models catalog: catalog failure signals outage, not capability', () => {
  it('catalog reject shows outage header and built-in fallback, not "can run on this server"', async () => {
    const app = renderApp({
      hash: '#/models',
      token: 'testuser',
      seed: {
        fail: {
          '/api/v1/ml/models': { status: 500, detail: 'Catalog is down' },
        },
      },
    });
    backend = app.backend;

    // Fallback list is still rendered (Random_Forest is a fallback entry).
    expect(await screen.findByText('Random_Forest')).toBeInTheDocument();

    // Outage / degraded header instead of a capability count over fallback entries.
    // The notice below repeats "could not be loaded", so pin the header phrase.
    expect(
      await screen.findByText(/what this server supports is unknown/i)
    ).toBeInTheDocument();
    expect(screen.queryByText(/can run on this server/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/8 of 8/)).not.toBeInTheDocument();

    // Notice is bad severity and labels the fallback.
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/built-in list instead/i);
    expect(alert.className).toContain('notice-bad');
  });
});

describe('models catalog: success still reports capability', () => {
  it('successful catalog shows the runnable count', async () => {
    const app = renderApp({
      hash: '#/models',
      token: 'testuser',
      seed: {
        models: [
          {
            name: 'Fake_Forest',
            category: 'classification',
            description: 'A fake model for tests.',
            parameters: {},
            optimization: [],
            test_results: null,
          },
          {
            name: 'Fake_Linear',
            category: 'regression',
            description: 'A fake regression model.',
            parameters: {},
            optimization: [],
            test_results: null,
          },
        ],
      },
    });
    backend = app.backend;

    expect(await screen.findByText('Fake_Forest')).toBeInTheDocument();
    expect(
      await screen.findByText('2 of 2 can run on this server.')
    ).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('models catalog: R3a search filter + disclosure cards', () => {
  it('search filters the catalog and hides non-matching models', async () => {
    const app = renderApp({
      hash: '#/models',
      token: 'testuser',
      seed: {
        models: [
          {
            name: 'Fake_Forest',
            category: 'classification',
            description: 'A fake model for tests.',
            parameters: {},
            optimization: [],
            test_results: null,
          },
          {
            name: 'Fake_Linear',
            category: 'regression',
            description: 'A fake regression model.',
            parameters: {},
            optimization: [],
            test_results: null,
          },
        ],
      },
    });
    backend = app.backend;

    expect(await screen.findByText('Fake_Forest')).toBeInTheDocument();
    expect(screen.getByText('Fake_Linear')).toBeInTheDocument();

    // R3a: the search field carries the shared catalog-search class.
    const search = screen.getByLabelText(/find a model/i);
    expect(search.className).toContain('catalog-search');

    fireEvent.change(search, { target: { value: 'Fake_Forest' } });
    expect(screen.getByText('Fake_Forest')).toBeInTheDocument();
    expect(screen.queryByText('Fake_Linear')).not.toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'matchesnothing' } });
    expect(
      await screen.findByText('No model matches that search.')
    ).toBeInTheDocument();
    expect(screen.queryByText('Fake_Forest')).not.toBeInTheDocument();
  });

  it('disclosure rows carry the shared model-row/detail classes and marker', async () => {
    const app = renderApp({ hash: '#/models', token: 'testuser' });
    backend = app.backend;

    expect(await screen.findByText('Random_Forest')).toBeInTheDocument();

    // R3a shared classes (absent before the redesign).
    const row = document.querySelector('.model-row');
    expect(row).not.toBeNull();
    const summary = document.querySelector('.model-summary');
    expect(summary).not.toBeNull();
    expect(summary.className).toContain('disclosure-summary');
    expect(summary.querySelector('.disclosure-marker')).not.toBeNull();
    expect(document.querySelector('.model-detail-grid')).not.toBeNull();
    expect(document.querySelector('.catalog-group')).not.toBeNull();
  });
});
