import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
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

describe('predict: result announces a summary, not the whole result', () => {
  it('single role=status with result summary; result container has no aria-live', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: completedPredictSeed(),
    });
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /^use this model$/i })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^predict$/i }));

    // The full result is still plain visible content.
    expect(await screen.findByText('a', { exact: true })).toBeInTheDocument();

    const statuses = screen.getAllByRole('status');
    expect(statuses).toHaveLength(1);
    const status = statuses[0];
    expect(status).toHaveTextContent(/1 prediction.*a/i);

    // The result container that wraps the announcement no longer live-announces.
    expect(status.parentElement).not.toHaveAttribute('aria-live');
    expect(document.querySelectorAll('[aria-live]')).toHaveLength(0);

    // The summary is short, not a dump of the probabilities.
    expect(status.textContent).not.toMatch(/0\.9/);
  });
});

function seedForKind(requestKind, schemaExtra = {}, predicts = undefined) {
  const base = completedPredictSeed();
  const schema = {
    run_id: 1,
    kind: 'tabular',
    model_name: 'Random_Forest',
    task_type: 'classification',
    label_column: 'label',
    features: [
      { name: 'f1', kind: 'numeric', min: 0, max: 1, default: 0.5 },
      { name: 'f2', kind: 'categorical', categories: ['a', 'b'], default: 'a' },
    ],
    dropped_columns: [],
    classes: ['a', 'b'],
    max_rows: 1000,
    output: 'A class label',
    request_kind: requestKind,
    ...schemaExtra,
  };
  return {
    ...base,
    schemas: { 1: schema },
    ...(predicts ? { predicts: { 1: predicts } } : {}),
  };
}

function predictCall(backend, pathname = '/api/v1/ml/runs/1/predict') {
  const calls = backend.calls.filter((c) => c.pathname === pathname);
  return calls[calls.length - 1];
}

describe('predict: R3b redesign keeps the predict request shapes', () => {
  it('rows form posts {rows:[row]} with numeric coercion (and R3b hooks)', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: seedForKind('rows'),
    });
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /^use this model$/i })
    ).toBeInTheDocument();
    // R3b shared layout hooks (absent before the redesign).
    expect(document.querySelector('.predict-panel')).not.toBeNull();
    expect(document.querySelector('.predict-segmented')).not.toBeNull();
    expect(document.querySelector('.predict-form-grid')).not.toBeNull();
    expect(document.querySelector('.predict-actions')).not.toBeNull();
    expect(screen.getByRole('button', { name: /one row/i })).toHaveAttribute(
      'aria-pressed',
      'true'
    );

    fireEvent.change(screen.getByLabelText(/^f1/i), {
      target: { value: '0.7' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^predict$/i }));

    expect(await screen.findByText('a', { exact: true })).toBeInTheDocument();
    expect(document.querySelector('.predict-result')).not.toBeNull();
    const call = predictCall(backend);
    expect(call.method).toBe('POST');
    expect(Object.keys(call.body)).toEqual(['rows']);
    expect(call.body.rows).toHaveLength(1);
    expect(call.body.rows[0]).toEqual({ f1: 0.7, f2: 'a' });
  });

  it('rows JSON posts {rows:[...]} verbatim', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: seedForKind('rows'),
    });
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /^use this model$/i })
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /several rows/i }));
    const textarea = await screen.findByLabelText(/rows as json/i);
    fireEvent.change(textarea, {
      target: { value: '[{"f1":0.1},{"f1":0.2}]' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^predict$/i }));

    await waitFor(() => {
      const call = predictCall(backend);
      expect(call).toBeDefined();
      expect(call.body.rows).toHaveLength(2);
    });
    const call = predictCall(backend);
    expect(Object.keys(call.body)).toEqual(['rows']);
    expect(call.body.rows).toEqual([{ f1: 0.1 }, { f1: 0.2 }]);
  });

  it('texts posts {texts:[...]} one per line', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: seedForKind('texts'),
    });
    backend = app.backend;

    const input = await screen.findByLabelText(/one text per line/i);
    fireEvent.change(input, { target: { value: 'hello\nworld' } });
    fireEvent.click(screen.getByRole('button', { name: /^predict$/i }));

    await waitFor(() => {
      const call = predictCall(backend);
      expect(call).toBeDefined();
      expect(call.body.texts).toEqual(['hello', 'world']);
    });
    const call = predictCall(backend);
    expect(Object.keys(call.body)).toEqual(['texts']);
  });

  it('prompt posts {prompt,max_new_tokens} via Generate', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: seedForKind('prompt'),
    });
    backend = app.backend;

    const input = await screen.findByLabelText(
      /the model continues this text/i
    );
    fireEvent.change(input, { target: { value: 'Once upon a time' } });
    fireEvent.change(screen.getByLabelText(/longest answer.*in tokens/i), {
      target: { value: '32' },
    });
    expect(
      screen.getByRole('button', { name: /^generate$/i })
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^generate$/i }));

    await waitFor(() => {
      const call = predictCall(backend);
      expect(call).toBeDefined();
      expect(call.body.prompt).toBe('Once upon a time');
    });
    const call = predictCall(backend);
    expect(Object.keys(call.body).sort()).toEqual([
      'max_new_tokens',
      'prompt',
    ]);
    expect(call.body.max_new_tokens).toBe(32);
  });

  it('window_rows posts {window_rows:[[numbers]]}', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: seedForKind('window_rows', {
        window: 2,
        features: ['y', 'x'],
      }),
    });
    backend = app.backend;

    const input = await screen.findByLabelText(
      /exactly 2 lines, oldest first/i
    );
    fireEvent.change(input, { target: { value: '1, 2\n3, 4' } });
    fireEvent.click(screen.getByRole('button', { name: /^predict$/i }));

    await waitFor(() => {
      const call = predictCall(backend);
      expect(call).toBeDefined();
      expect(call.body.window_rows).toEqual([
        [1, 2],
        [3, 4],
      ]);
    });
    const call = predictCall(backend);
    expect(Object.keys(call.body)).toEqual(['window_rows']);
  });

  it('node_ids posts {node_ids:[...]}', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: seedForKind('node_ids', { nodes: 10 }),
    });
    backend = app.backend;

    const input = await screen.findByLabelText(/node ids from the graph/i);
    fireEvent.change(input, { target: { value: 'n1, n2' } });
    fireEvent.click(screen.getByRole('button', { name: /^predict$/i }));

    await waitFor(() => {
      const call = predictCall(backend);
      expect(call).toBeDefined();
      expect(call.body.node_ids).toEqual(['n1', 'n2']);
    });
    const call = predictCall(backend);
    expect(Object.keys(call.body)).toEqual(['node_ids']);
  });

  it('state posts {state:number} for a table agent', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: seedForKind('state', { n_states: 3, n_actions: 2 }),
    });
    backend = app.backend;

    const input = await screen.findByLabelText(/a state from 0 to 2/i);
    fireEvent.change(input, { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: /^predict$/i }));

    await waitFor(() => {
      const call = predictCall(backend);
      expect(call).toBeDefined();
      expect(call.body.state).toBe(2);
    });
    const call = predictCall(backend);
    expect(Object.keys(call.body)).toEqual(['state']);
  });

  it('image posts FormData with a single file to /predict-image', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: seedForKind('image'),
    });
    backend = app.backend;

    const input = await screen.findByLabelText(/an image of one of/i);
    const file = new File(['fake-png'], 'cat.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: /^predict$/i }));

    await waitFor(() => {
      const call = predictCall(backend, '/api/v1/ml/runs/1/predict-image');
      expect(call).toBeDefined();
      expect(call.method).toBe('POST');
      expect(call.rawBody).toBeInstanceOf(FormData);
      expect(call.rawBody.get('file')).toBeInstanceOf(File);
    });
    const call = predictCall(backend, '/api/v1/ml/runs/1/predict-image');
    expect(call.rawBody.get('file').name).toBe('cat.png');
    // The JSON predict endpoint is never called for an image.
    expect(backend.calls.filter((c) => c.pathname === '/api/v1/ml/runs/1/predict')).toHaveLength(0);
  });
});

describe('predict: R5 segmented control hardening', () => {
  it('input-style buttons are non-submit buttons in DOM order with pressed state', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: seedForKind('rows'),
    });
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /^use this model$/i })
    ).toBeInTheDocument();

    const oneRow = screen.getByRole('button', { name: /one row/i });
    const severalRows = screen.getByRole('button', { name: /several rows/i });

    // Non-submit so the control stays safe if the panel is ever nested in a
    // form (absent pre-R5), and DOM order matches visual order for keyboards.
    expect(oneRow).toHaveAttribute('type', 'button');
    expect(severalRows).toHaveAttribute('type', 'button');
    expect(
      oneRow.compareDocumentPosition(severalRows) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();

    expect(oneRow).toHaveAttribute('aria-pressed', 'true');
    expect(severalRows).toHaveAttribute('aria-pressed', 'false');
    severalRows.focus();
    expect(document.activeElement).toBe(severalRows);
  });
});

describe('predict: C1 segmented control arrow-key navigation', () => {
  it('ArrowRight selects+focuses Several rows, ArrowLeft back, Home/End, non-arrow no-op', async () => {
    const app = renderApp({
      hash: '#/run-details/1',
      token: 'testuser',
      seed: seedForKind('rows'),
    });
    backend = app.backend;

    expect(
      await screen.findByRole('heading', { name: /^use this model$/i })
    ).toBeInTheDocument();

    const oneRow = screen.getByRole('button', { name: /one row/i });
    const severalRows = screen.getByRole('button', { name: /several rows/i });

    // Keep Tab behavior: both buttons are tabbable (no -1 tabIndex roving).
    expect(oneRow.tabIndex).toBe(0);
    expect(severalRows.tabIndex).toBe(0);

    oneRow.focus();
    expect(document.activeElement).toBe(oneRow);

    fireEvent.keyDown(oneRow, { key: 'ArrowRight' });
    expect(severalRows).toHaveAttribute('aria-pressed', 'true');
    expect(oneRow).toHaveAttribute('aria-pressed', 'false');
    expect(document.activeElement).toBe(severalRows);
    expect(await screen.findByLabelText(/rows as json/i)).toBeInTheDocument();

    fireEvent.keyDown(severalRows, { key: 'ArrowLeft' });
    expect(oneRow).toHaveAttribute('aria-pressed', 'true');
    expect(severalRows).toHaveAttribute('aria-pressed', 'false');
    expect(document.activeElement).toBe(oneRow);

    fireEvent.keyDown(oneRow, { key: 'End' });
    expect(severalRows).toHaveAttribute('aria-pressed', 'true');
    expect(document.activeElement).toBe(severalRows);

    fireEvent.keyDown(severalRows, { key: 'Home' });
    expect(oneRow).toHaveAttribute('aria-pressed', 'true');
    expect(document.activeElement).toBe(oneRow);

    // Up/Down alias Left/Right.
    fireEvent.keyDown(oneRow, { key: 'ArrowDown' });
    expect(severalRows).toHaveAttribute('aria-pressed', 'true');
    expect(document.activeElement).toBe(severalRows);
    fireEvent.keyDown(severalRows, { key: 'ArrowUp' });
    expect(oneRow).toHaveAttribute('aria-pressed', 'true');
    expect(document.activeElement).toBe(oneRow);

    // Non-arrow key is a no-op: pressed state and mode unchanged.
    fireEvent.keyDown(oneRow, { key: 'a' });
    expect(oneRow).toHaveAttribute('aria-pressed', 'true');
    expect(severalRows).toHaveAttribute('aria-pressed', 'false');
    expect(document.activeElement).toBe(oneRow);
  });
});
