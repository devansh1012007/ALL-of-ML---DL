import React from 'react';
import { render, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import App from '../App.jsx';

// ---------------------------------------------------------------------------
// Helpers for the frontend test harness (plan P1).
//
// - installFakeBackend(seed) mocks global.fetch at the FETCH level and returns
//   Response-like objects ({ ok, status, json(), blob(), text() }) matching the
//   backend shapes in backend/app/main.py + backend/app/admin.py. It never
//   returns parsed objects and never requires a real Response.
// - renderApp({ hash, token, seed }) renders the real <App/> black-box, seeds
//   localStorage.prime_token with a crafted decodable JWT, sets the hash
//   before mount, and returns { backend, ...testingLibraryView }.
//
// State is mutable: tests may write to backend.state (for example
// `backend.state.me.role = 'user'` or
// `backend.state.fail['/api/v1/ml/models'] = { status: 500, detail: '...' }`)
// and later fetches observe the new state. Every call is recorded in
// backend.calls as { method, url, pathname, searchParams, rawBody, body,
// headers } so tests can assert the fetch contract without mocking the
// component under test.
//
// Polling (5s runs list, 2s run details, 1.5s run events, 5s admin queue)
// uses setInterval/setTimeout. Tests must not leak timers: afterEach should
// call cleanup(), backend.restore(), clear localStorage + hash, and
// vi.useRealTimers(). Tests that need fake timers control them explicitly.
//
// Auth (finding 2, documented, not enforced here): the fake backend does not
// inspect the Authorization header. App gates first — without a stored token
// it renders the sign-in form and never calls the API — and renders tests
// seed localStorage.prime_token via renderApp({ token }). 401/403 behaviour
// is exercised by setting backend.state.fail['<pathname>'] = { status: 401,
// detail: '...' }, which short-circuits every later fetch to that path. This
// is deliberate: adding header enforcement here would break existing smokes.
//
// Streaming (finding 3, intentionally out of scope): the backend exposes
// GET /api/v1/ml/runs/{id}/stream as an optional SSE form (text/event-stream),
// but App does not consume it: RunDetails polls GET .../runs/{id}/events
// instead, and no EventSource or getReader() stream is used. No /stream
// handler is provided on purpose; a request to it returns the generic
// "No fake handler" 404 below. Add one only if a future App version starts
// using the stream.
// ---------------------------------------------------------------------------

function base64UrlEncode(text) {
  const utf8 = unescape(encodeURIComponent(text));
  const base64 = btoa(utf8);
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function makeTestToken(username) {
  const header = base64UrlEncode(JSON.stringify({ alg: 'none', typ: 'JWT' }));
  const payload = base64UrlEncode(
    JSON.stringify({ sub: String(username || 'testuser'), exp: 9999999999 })
  );
  return `${header}.${payload}.test-signature`;
}

function clone(value) {
  return value === undefined ? value : JSON.parse(JSON.stringify(value));
}

function defaultUsage() {
  return {
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
  };
}

function defaultModels() {
  return [
    {
      name: 'Random_Forest',
      category: 'classification',
      description: 'Random Forest classifier for tabular data.',
      parameters: {},
      optimization: [],
      test_results: null,
    },
    {
      name: 'MLR',
      category: 'regression',
      description: 'Multiple Linear Regression for numeric prediction.',
      parameters: {},
      optimization: [],
      test_results: null,
    },
  ];
}

function defaultDatasets() {
  return [
    {
      id: 1,
      name: 'sample_customer_churn.csv',
      source: 'builtin',
      kind: 'tabular',
      content_sha256: 'abc123',
      size_bytes: 12345,
      row_count: 100,
      columns: [{ name: 'age' }, { name: 'label' }],
      column_count: 2,
      label_column: 'label',
      owner_id: null,
    },
  ];
}

function modeDescriptions() {
  return {
    manual:
      'User-defined hyperparameters - full control over training settings',
    auto_tune: 'Randomized hyperparameter search over a curated per-model space',
    auto_fine_tune: 'Local hyperparameter search around the current configuration',
    llm_fine_tune:
      'AI-guided parameters via Google Gemini (requires GOOGLE_API_KEY and the google-generativeai package)',
    auto_search: 'Model selection over multiple candidates - not Bayesian optimization',
  };
}

function defaultPresets() {
  return [
    {
      name: 'conservative',
      description: 'Low learning rate, high regularization, fewer iterations',
    },
    {
      name: 'balanced',
      description: 'Default settings optimized for most use cases',
    },
    {
      name: 'aggressive',
      description: 'High learning rate, low regularization, more iterations',
    },
  ];
}

function defaultProfiles() {
  return [
    {
      id: 1,
      name: 'free',
      max_concurrent_runs: 1,
      max_queued_runs: 5,
      max_runs_per_day: 20,
      max_run_seconds: 600,
      max_run_memory_mb: 2048,
      max_cpu_seconds_per_month: 7200,
      max_storage_bytes: 500 * 1024 * 1024,
      max_datasets: 10,
      max_upload_bytes: 50 * 1024 * 1024,
      max_rows: 500000,
      max_predict_rows_per_request: 1000,
      max_predict_requests_per_minute: 60,
      allowed_categories: ['classification', 'regression'],
      gpu_allowed: false,
      artifact_keep_runs: null,
      artifact_keep_days: null,
    },
    {
      id: 2,
      name: 'standard',
      max_concurrent_runs: 2,
      max_queued_runs: 20,
      max_runs_per_day: 100,
      max_run_seconds: 3600,
      max_run_memory_mb: 4096,
      max_cpu_seconds_per_month: 30000,
      max_storage_bytes: 5 * 1024 * 1024 * 1024,
      max_datasets: 50,
      max_upload_bytes: 200 * 1024 * 1024,
      max_rows: 2000000,
      max_predict_rows_per_request: 5000,
      max_predict_requests_per_minute: 300,
      allowed_categories: null,
      gpu_allowed: false,
      artifact_keep_runs: null,
      artifact_keep_days: null,
    },
    {
      id: 3,
      name: 'unlimited',
      max_concurrent_runs: null,
      max_queued_runs: null,
      max_runs_per_day: null,
      max_run_seconds: null,
      max_run_memory_mb: null,
      max_cpu_seconds_per_month: null,
      max_storage_bytes: null,
      max_datasets: null,
      max_upload_bytes: null,
      max_rows: null,
      max_predict_rows_per_request: null,
      max_predict_requests_per_minute: null,
      allowed_categories: null,
      gpu_allowed: true,
      artifact_keep_runs: null,
      artifact_keep_days: null,
    },
  ];
}

function defaultUsers() {
  return [
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
  ];
}

function defaultAdminUsage() {
  return [
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
  ];
}

function defaultSchema(runId, modelName) {
  return {
    run_id: runId,
    kind: 'tabular',
    model_name: modelName || 'Random_Forest',
    task_type: 'classification',
    label_column: 'label',
    features: [
      { name: 'f1', kind: 'numeric', min: 0, max: 1, default: 0.5 },
      { name: 'f2', kind: 'categorical', categories: ['a', 'b'], default: 'a' },
    ],
    dropped_columns: [],
    classes: ['a', 'b'],
    max_rows: 1000,
    request_kind: 'rows',
    output: 'A class label',
  };
}

function defaultPredict(runId, modelName, nRows) {
  const count = Number.isFinite(nRows) && nRows > 0 ? nRows : 1;
  const predictions = Array.from({ length: count }, () => 'a');
  const probabilities = Array.from({ length: count }, () => ({ a: 0.9, b: 0.1 }));
  return {
    run_id: runId,
    model_name: modelName || 'Random_Forest',
    request_kind: 'rows',
    n_rows: count,
    task_type: 'classification',
    predictions,
    classes: ['a', 'b'],
    probabilities,
    warnings: [],
  };
}

function buildDefaultState() {
  return {
    me: {
      id: 1,
      username: 'testuser',
      role: 'user',
      status: 'active',
      registration_mode: 'open',
      usage: defaultUsage(),
    },
    models: defaultModels(),
    datasets: defaultDatasets(),
    trainingModes: {
      modes: ['manual', 'auto_tune', 'auto_fine_tune', 'llm_fine_tune', 'auto_search'],
      descriptions: modeDescriptions(),
    },
    trainingPresets: defaultPresets(),
    runs: [],
    runDetails: {},
    events: {},
    schemas: {},
    predicts: {},
    trainResult: { run_id: 1, status: 'queued', artifact_path: null, metrics: null },
    admin: {
      users: defaultUsers(),
      usage: defaultAdminUsage(),
      profiles: defaultProfiles(),
      queue: [],
      invites: [],
      audit: [],
    },
    fail: {},
  };
}

function applySeed(seed) {
  const state = buildDefaultState();
  if (!seed) return state;
  if (seed.me) {
    const usage = { ...state.me.usage, ...(seed.me.usage || {}) };
    if (seed.me.usage && seed.me.usage.limits) {
      usage.limits = { ...state.me.usage.limits, ...seed.me.usage.limits };
    }
    if (seed.me.usage && seed.me.usage.resets_at) {
      usage.resets_at = { ...state.me.usage.resets_at, ...seed.me.usage.resets_at };
    }
    state.me = { ...state.me, ...seed.me, usage };
  }
  if (seed.models !== undefined) state.models = clone(seed.models);
  if (seed.datasets !== undefined) state.datasets = clone(seed.datasets);
  if (seed.trainingModes !== undefined) state.trainingModes = clone(seed.trainingModes);
  if (seed.modes !== undefined) {
    state.trainingModes.modes = clone(seed.modes);
  }
  if (seed.trainingPresets !== undefined) state.trainingPresets = clone(seed.trainingPresets);
  if (seed.presets !== undefined) state.trainingPresets = clone(seed.presets);
  if (seed.runs !== undefined) state.runs = clone(seed.runs);
  if (seed.runDetails !== undefined) state.runDetails = clone(seed.runDetails);
  if (seed.events !== undefined) state.events = clone(seed.events);
  if (seed.schemas !== undefined) state.schemas = clone(seed.schemas);
  if (seed.predicts !== undefined) state.predicts = clone(seed.predicts);
  if (seed.trainResult !== undefined) state.trainResult = clone(seed.trainResult);
  if (seed.admin !== undefined) {
    state.admin = { ...state.admin, ...clone(seed.admin) };
  }
  if (seed.fail !== undefined) state.fail = { ...state.fail, ...clone(seed.fail) };
  return state;
}

function makeJsonResponse(data, status) {
  const code = status === undefined ? 200 : status;
  return {
    ok: code >= 200 && code < 300,
    status: code,
    json: async () => clone(data),
    text: async () => JSON.stringify(data),
    blob: async () =>
      new Blob([JSON.stringify(data)], { type: 'application/json' }),
  };
}

function makeErrorResponse(status, detail) {
  return makeJsonResponse({ detail }, status);
}

function makeBlobResponse() {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      detail: 'Artifact is binary; use blob().',
    }),
    text: async () => 'fake-artifact',
    blob: async () =>
      new Blob(['fake-artifact'], { type: 'application/zip' }),
  };
}

function parseBody(rawBody) {
  if (rawBody === null || rawBody === undefined) return null;
  if (typeof rawBody === 'string') {
    try {
      return JSON.parse(rawBody);
    } catch {
      return rawBody;
    }
  }
  if (rawBody instanceof URLSearchParams) {
    return Object.fromEntries(rawBody.entries());
  }
  return rawBody;
}

function findRunDetail(state, id) {
  const key = String(id);
  if (state.runDetails[key]) return state.runDetails[key];
  const summary = state.runs.find((r) => String(r.id) === key);
  if (!summary) return null;
  return {
    dataset_hash: 'abc123',
    label_column: 'label',
    random_state: 42,
    test_size: 0.2,
    task_type: 'classification',
    metrics: { accuracy: 0.9, baseline_accuracy: 0.5 },
    hyperparameters: {},
    artifact_path: null,
    job_kind: 'train',
    mode: 'manual',
    env_id: null,
    optimize_metric: 'accuracy',
    model_candidates: null,
    tags: [],
    note: null,
    has_charts: false,
    heartbeat_at: null,
    ...summary,
  };
}

export function installFakeBackend(seed) {
  const state = applySeed(seed);
  const calls = [];
  const originalFetch = global.fetch;

  const fakeFetch = async (input, options) => {
    const rawUrl =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.href
          : input && input.url
            ? input.url
            : String(input);
    const method = (
      (options && options.method) ||
      (input && input.method) ||
      'GET'
    ).toUpperCase();
    const headers =
      (options && options.headers) || (input && input.headers) || {};
    const rawBody =
      options && 'body' in options
        ? options.body
        : input && typeof input === 'object' && 'body' in input
          ? input.body
          : null;

    let parsed;
    try {
      parsed = new URL(rawUrl, 'http://localhost:8010');
    } catch {
      parsed = new URL('http://localhost:8010/');
    }
    const pathname = parsed.pathname;
    const searchParams = Object.fromEntries(parsed.searchParams.entries());
    const body = parseBody(rawBody);

    calls.push({ method, url: rawUrl, pathname, searchParams, rawBody, body, headers });

    const fail = state.fail ? state.fail[pathname] : null;
    if (fail && fail.network) {
      throw new TypeError(fail.message || 'Failed to fetch');
    }
    if (fail) {
      return makeErrorResponse(fail.status || 500, fail.detail || 'Fake backend failure');
    }

    // -- auth ----------------------------------------------------------------
    if (pathname === '/token' && method === 'POST') {
      const username = body && body.username;
      const password = body && body.password;
      if (!username || !password) {
        return makeErrorResponse(400, 'Incorrect username or password');
      }
      const existing =
        state.admin.users.find((u) => u.username === username) ||
        (state.me.username === username ? state.me : null);
      const role = existing ? existing.role : 'user';
      const token = makeTestToken(username);
      return makeJsonResponse({
        access_token: token,
        token_type: 'bearer',
        role,
        registration_mode: state.me.registration_mode || 'open',
        refresh_token: 'fake-refresh-token',
        expires_in: 3600,
      });
    }
    if (pathname === '/api/v1/register' && method === 'POST') {
      const username = body && body.username;
      const password = body && body.password;
      const reserved = ['anonymous', 'admin', 'root', 'system'];
      if (!username || !password || String(password).length < 8) {
        return makeErrorResponse(400, 'Password must be at least 8 characters.');
      }
      if (reserved.includes(String(username))) {
        return makeErrorResponse(400, `Username '${username}' is reserved.`);
      }
      if (
        state.admin.users.some((u) => u.username === username) ||
        state.me.username === username
      ) {
        return makeErrorResponse(409, `Username '${username}' is already taken`);
      }
      const nextId =
        Math.max(0, ...state.admin.users.map((u) => u.id || 0), 0) + 1;
      state.admin.users.push({
        id: nextId,
        username,
        role: 'user',
        status: 'active',
        email: null,
        quota_profile_id: null,
        created_at: '2026-11-08T00:00:00Z',
        last_login_at: null,
        usage: null,
      });
      return makeJsonResponse({
        message: 'User registered successfully',
        status: 'active',
        note: null,
      });
    }
    if (pathname === '/api/v1/me' && method === 'GET') {
      return makeJsonResponse(clone(state.me));
    }

    // -- catalog / datasets / modes ------------------------------------------
    if (pathname === '/api/v1/ml/models' && method === 'GET') {
      return makeJsonResponse(clone(state.models));
    }
    if (pathname === '/api/v1/ml/model-categories' && method === 'GET') {
      const categories = [...new Set(state.models.map((m) => m.category))];
      return makeJsonResponse({ categories });
    }
    if (pathname === '/api/v1/ml/model-details' && method === 'GET') {
      const modelName = searchParams.model_name;
      if (modelName) {
        const found = state.models.find((m) => m.name === modelName);
        if (!found) {
          return makeErrorResponse(404, `Model '${modelName}' not found`);
        }
        return makeJsonResponse(clone(found));
      }
      return makeJsonResponse({ models: clone(state.models) });
    }
    if (pathname === '/api/v1/ml/training-modes' && method === 'GET') {
      return makeJsonResponse(clone(state.trainingModes));
    }
    if (pathname === '/api/v1/ml/training-presets' && method === 'GET') {
      return makeJsonResponse({ presets: clone(state.trainingPresets) });
    }
    if (pathname === '/api/v1/ml/suggest' && method === 'POST') {
      return makeJsonResponse({ suggested_hyperparameters: {} });
    }
    if (pathname === '/api/v1/ml/datasets' && method === 'GET') {
      return makeJsonResponse({ datasets: clone(state.datasets) });
    }
    if (pathname === '/api/v1/ml/datasets/upload' && method === 'POST') {
      let fileName = 'uploaded.csv';
      if (rawBody && typeof rawBody.get === 'function') {
        const file = rawBody.get('file');
        if (file && file.name) fileName = file.name;
      }
      const nextId =
        Math.max(0, ...state.datasets.map((d) => d.id || 0), 0) + 1;
      const dataset = {
        id: nextId,
        name: fileName,
        source: 'upload',
        kind: 'tabular',
        content_sha256: 'fake',
        size_bytes: 1000,
        row_count: 10,
        columns: [{ name: 'label' }],
        column_count: 1,
        label_column: 'label',
        owner_id: state.me.id,
      };
      state.datasets.push(dataset);
      return makeJsonResponse(clone(dataset));
    }
    {
      const dsProfile = pathname.match(/^\/api\/v1\/ml\/datasets\/([^/]+)\/profile$/);
      if (dsProfile && method === 'GET') {
        const id = Number(dsProfile[1]);
        const dataset = state.datasets.find((d) => d.id === id);
        if (!dataset) return makeErrorResponse(404, 'Dataset not found');
        return makeJsonResponse({
          dataset_id: dataset.id,
          name: dataset.name,
          columns: clone(dataset.columns || []),
          row_count: dataset.row_count,
          label_distribution: {},
          duplicate_fraction: 0,
          correlated_pairs: [],
        });
      }
      const dsOne = pathname.match(/^\/api\/v1\/ml\/datasets\/([^/]+)$/);
      if (dsOne) {
        const id = Number(dsOne[1]);
        const dataset = state.datasets.find((d) => d.id === id);
        if (!dataset) return makeErrorResponse(404, 'Dataset not found');
        if (method === 'GET') return makeJsonResponse(clone(dataset));
        if (method === 'DELETE') {
          state.datasets = state.datasets.filter((d) => d.id !== id);
          return makeJsonResponse({ deleted: id });
        }
      }
    }

    // -- training -------------------------------------------------------------
    if (pathname === '/api/v1/ml/train' && method === 'POST') {
      const nextId =
        Math.max(
          0,
          ...state.runs.map((r) => r.id || 0),
          ...Object.keys(state.runDetails).map((k) => Number(k) || 0),
          0
        ) + 1;
      const modelName = (body && body.model_name) || 'Random_Forest';
      const runSummary = {
        id: nextId,
        model_name: modelName,
        dataset_source: 'local',
        dataset_tag: 'sample.csv',
        dataset_id: (body && body.dataset_id) || null,
        mode: (body && body.mode) || 'manual',
        env_id: null,
        optimize_metric: 'accuracy',
        model_candidates: null,
        status: 'queued',
        job_kind: 'train',
        artifact_path: null,
        artifact_removed: false,
        metrics: null,
        tags: [],
        note: null,
        created_at: '2026-11-08T00:00:00Z',
        updated_at: '2026-11-08T00:00:00Z',
        started_at: null,
        finished_at: null,
        wall_seconds: null,
      };
      state.runs.unshift(runSummary);
      state.runDetails[String(nextId)] = {
        dataset_hash: 'abc123',
        label_column: 'label',
        random_state: 42,
        test_size: 0.2,
        task_type: 'classification',
        hf_dataset_url: null,
        hyperparameters: (body && body.hyperparameters) || {},
        ...clone(runSummary),
      };
      return makeJsonResponse({
        run_id: nextId,
        status: 'queued',
        artifact_path: null,
        metrics: null,
      });
    }

    // -- runs -----------------------------------------------------------------
    if (pathname === '/api/v1/ml/runs/compare' && method === 'GET') {
      const idsRaw = searchParams.ids || '';
      const ids = idsRaw
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map(Number);
      if (ids.length < 2 || ids.length > 6) {
        return makeErrorResponse(422, 'Compare between 2 and 6 runs.');
      }
      const facts = [];
      for (const rid of ids) {
        const run = findRunDetail(state, rid);
        if (!run) return makeErrorResponse(404, `Training run ${rid} not found`);
        facts.push({
          id: run.id,
          model_name: run.model_name,
          dataset_id: run.dataset_id || null,
          dataset_hash: run.dataset_hash || null,
          label_column: run.label_column || null,
          random_state: run.random_state || null,
          test_size: run.test_size || null,
          task_type: run.task_type || null,
          metrics: run.metrics || null,
          hyperparameters: run.hyperparameters || {},
          parameters: (run.metrics || {}).model_parameters || null,
          preprocessing: (run.metrics || {}).preprocessing || null,
          cv: (run.metrics || {}).cv || null,
        });
      }
      return makeJsonResponse({ runs: facts, differences: [], comparable: true, note: null });
    }
    if (pathname === '/api/v1/ml/runs/delete-bulk' && method === 'POST') {
      const ids = (body && body.ids) || [];
      const deleted = [];
      const refused = [];
      for (const rid of ids) {
        const run = findRunDetail(state, rid);
        if (!run) {
          refused.push({ id: rid, reason: 'No such run.' });
          continue;
        }
        if (run.status === 'queued' || run.status === 'running') {
          refused.push({ id: rid, reason: 'The run is queued or running; cancel it first.' });
          continue;
        }
        state.runs = state.runs.filter((r) => r.id !== rid);
        delete state.runDetails[String(rid)];
        deleted.push({ id: rid, deleted: true });
      }
      return makeJsonResponse({ deleted, refused });
    }
    if (pathname === '/api/v1/ml/runs' && method === 'GET') {
      let items = clone(state.runs);
      if (searchParams.status_filter) {
        items = items.filter((r) => r.status === searchParams.status_filter);
      }
      if (searchParams.model) {
        items = items.filter((r) => r.model_name === searchParams.model);
      }
      if (searchParams.q) {
        const needle = String(searchParams.q).toLowerCase();
        items = items.filter(
          (r) =>
            String(r.model_name || '').toLowerCase().includes(needle) ||
            String(r.dataset_tag || '').toLowerCase().includes(needle)
        );
      }
      const total = items.length;
      const limit = Math.max(1, Math.min(Number(searchParams.limit) || 20, 100));
      const offset = Math.max(0, Number(searchParams.offset) || 0);
      const page = items.slice(offset, offset + limit);
      return makeJsonResponse({ items: page, total, limit, offset });
    }
    {
      const sub = pathname.match(/^\/api\/v1\/ml\/runs\/([^/]+)\/(schema|events|charts|cancel|artifact|predict|predict-image)$/);
      if (sub) {
        const runId = sub[1];
        const action = sub[2];
        const run = findRunDetail(state, runId);
        if (action === 'schema' && method === 'GET') {
          if (!run) return makeErrorResponse(404, 'Training run not found');
          if (run.status !== 'completed') {
            return makeErrorResponse(409, `The run is ${run.status}: only a completed run can predict.`);
          }
          const stored = state.schemas[runId];
          return makeJsonResponse(
            stored ? clone(stored) : defaultSchema(Number(runId), run.model_name)
          );
        }
        if ((action === 'predict' || action === 'predict-image') && method === 'POST') {
          if (!run) return makeErrorResponse(404, 'Training run not found');
          if (run.status !== 'completed') {
            return makeErrorResponse(409, `The run is ${run.status}: only a completed run can predict.`);
          }
          const stored = state.predicts[runId];
          if (stored) return makeJsonResponse(clone(stored));
          let nRows = 1;
          if (body) {
            if (Array.isArray(body.rows)) nRows = body.rows.length;
            else if (Array.isArray(body.texts)) nRows = body.texts.length;
            else if (Array.isArray(body.window_rows)) nRows = body.window_rows.length;
            else if (Array.isArray(body.node_ids)) nRows = body.node_ids.length;
            else if (body.prompt) nRows = 1;
          }
          return makeJsonResponse(
            { ...defaultPredict(Number(runId), run.model_name, nRows), request_kind: action === 'predict-image' ? 'image' : 'rows' }
          );
        }
        if (action === 'events' && method === 'GET') {
          if (!run) return makeErrorResponse(404, 'Training run not found');
          const after = Number(searchParams.after) || 0;
          const stored = state.events[runId];
          const allEvents =
            stored && stored.events ? clone(stored.events) : [];
          const filtered = allEvents.filter((e) => (e.seq || 0) > after);
          const lastSeq = filtered.length
            ? Math.max(...filtered.map((e) => e.seq || 0))
            : after;
          return makeJsonResponse({ run_id: Number(runId), last_seq: lastSeq, events: filtered });
        }
        if (action === 'charts' && method === 'GET') {
          if (!run) return makeErrorResponse(404, 'Training run not found');
          return makeJsonResponse({ run_id: Number(runId), charts: {} });
        }
        if (action === 'cancel' && method === 'POST') {
          if (!run) return makeErrorResponse(404, 'Training run not found');
          if (run.status !== 'queued' && run.status !== 'running') {
            return makeErrorResponse(409, `The run is already ${run.status}.`);
          }
          const was = run.status;
          run.status = 'cancelled';
          const summary = state.runs.find((r) => String(r.id) === String(runId));
          if (summary) summary.status = 'cancelled';
          const answer = { id: Number(runId), status: 'cancelled', was };
          if (was === 'running') {
            answer.note =
              'The training cannot be interrupted once it started: its result is discarded when it ends.';
          }
          return makeJsonResponse(answer);
        }
        if (action === 'artifact' && method === 'GET') {
          if (!run) return makeErrorResponse(404, 'Artifact not found');
          return makeBlobResponse();
        }
      }
      const one = pathname.match(/^\/api\/v1\/ml\/runs\/([^/]+)$/);
      if (one) {
        const runId = one[1];
        const run = findRunDetail(state, runId);
        if (method === 'GET') {
          if (!run) return makeErrorResponse(404, 'Training run not found');
          return makeJsonResponse(clone(run));
        }
        if (method === 'PATCH') {
          if (!run) return makeErrorResponse(404, 'Training run not found');
          const unknown = Object.keys(body || {}).filter(
            (k) => k !== 'tags' && k !== 'note'
          );
          if (unknown.length) {
            return makeErrorResponse(422, `Unknown field(s): ${unknown}; only tags and note are editable.`);
          }
          if ('tags' in (body || {})) run.tags = body.tags;
          if ('note' in (body || {})) run.note = body.note;
          const summary = state.runs.find((r) => String(r.id) === String(runId));
          if (summary) {
            if ('tags' in (body || {})) summary.tags = body.tags;
            if ('note' in (body || {})) summary.note = body.note;
          }
          return makeJsonResponse({ id: Number(runId), tags: run.tags, note: run.note });
        }
        if (method === 'DELETE') {
          if (!run) return makeErrorResponse(404, 'Training run not found');
          if (run.status === 'queued' || run.status === 'running') {
            return makeErrorResponse(409, 'The run is queued or running; cancel it first.');
          }
          state.runs = state.runs.filter((r) => String(r.id) !== String(runId));
          delete state.runDetails[String(runId)];
          return makeJsonResponse({ deleted: [{ id: Number(runId) }] });
        }
      }
    }

    // -- admin ----------------------------------------------------------------
    if (pathname === '/api/v1/admin/all-users' && method === 'GET') {
      return makeJsonResponse(
        state.admin.users.map((u) => ({ id: u.id, username: u.username, role: u.role }))
      );
    }
    if (pathname === '/api/v1/admin/users' && method === 'GET') {
      let items = clone(state.admin.users);
      if (searchParams.status_filter) {
        items = items.filter((u) => u.status === searchParams.status_filter);
      }
      if (searchParams.profile) {
        items = items.filter(
          (u) => String(u.quota_profile_id) === String(searchParams.profile)
        );
      }
      if (searchParams.q) {
        const needle = String(searchParams.q).toLowerCase();
        items = items.filter((u) =>
          String(u.username || '').toLowerCase().includes(needle)
        );
      }
      const total = items.length;
      const limit = Math.max(1, Math.min(Number(searchParams.limit) || 50, 200));
      const offset = Math.max(0, Number(searchParams.offset) || 0);
      return makeJsonResponse({
        items: items.slice(offset, offset + limit),
        total,
        limit,
        offset,
      });
    }
    {
      const approve = pathname.match(/^\/api\/v1\/admin\/users\/([^/]+)\/approve$/);
      if (approve && method === 'POST') {
        const user = state.admin.users.find((u) => String(u.id) === approve[1]);
        if (!user) return makeErrorResponse(404, 'User not found');
        if (user.status !== 'pending') {
          return makeErrorResponse(409, `The user is ${user.status}, not pending.`);
        }
        user.status = 'active';
        return makeJsonResponse(clone(user));
      }
      const suspend = pathname.match(/^\/api\/v1\/admin\/users\/([^/]+)\/suspend$/);
      if (suspend && method === 'POST') {
        const user = state.admin.users.find((u) => String(u.id) === suspend[1]);
        if (!user) return makeErrorResponse(404, 'User not found');
        user.status = 'suspended';
        return makeJsonResponse(clone(user));
      }
      const userOne = pathname.match(/^\/api\/v1\/admin\/users\/([^/]+)$/);
      if (userOne) {
        const user = state.admin.users.find((u) => String(u.id) === userOne[1]);
        if (method === 'GET') {
          if (!user) return makeErrorResponse(404, 'User not found');
          const usageForUser =
            state.admin.usage.find((x) => String(x.user_id) === String(user.id)) || null;
          return makeJsonResponse({ ...clone(user), usage: usageForUser });
        }
        if (method === 'PATCH') {
          if (!user) return makeErrorResponse(404, 'User not found');
          if (body) {
            if (body.status !== undefined) user.status = body.status;
            if (body.role !== undefined) user.role = body.role;
            if (body.quota_profile_id !== undefined) user.quota_profile_id = body.quota_profile_id;
            if (body.email !== undefined) user.email = body.email;
          }
          return makeJsonResponse(clone(user));
        }
        if (method === 'DELETE') {
          if (!user) return makeErrorResponse(404, 'User not found');
          if (user.role === 'admin') {
            const admins = state.admin.users.filter((u) => u.role === 'admin').length;
            if (admins <= 1) {
              return makeErrorResponse(409, 'The last admin cannot be deleted.');
            }
          }
          const removedId = user.id;
          state.admin.users = state.admin.users.filter((u) => u.id !== removedId);
          return makeJsonResponse({ id: removedId, deleted: true, files_removed: 0 });
        }
      }
    }
    if (pathname === '/api/v1/admin/usage' && method === 'GET') {
      return makeJsonResponse({ items: clone(state.admin.usage) });
    }
    if (pathname === '/api/v1/admin/quota-profiles' && method === 'GET') {
      return makeJsonResponse({ items: clone(state.admin.profiles) });
    }
    {
      const prof = pathname.match(/^\/api\/v1\/admin\/quota-profiles\/([^/]+)$/);
      if (prof && method === 'PUT') {
        const profile = state.admin.profiles.find(
          (p) => String(p.id) === prof[1]
        );
        if (!profile) return makeErrorResponse(404, 'Quota profile not found');
        if (body && body.values) Object.assign(profile, body.values);
        return makeJsonResponse(clone(profile));
      }
    }
    if (pathname === '/api/v1/admin/queue' && method === 'GET') {
      return makeJsonResponse({ items: clone(state.admin.queue) });
    }
    {
      const cancel = pathname.match(/^\/api\/v1\/admin\/queue\/([^/]+)\/cancel$/);
      if (cancel && method === 'POST') {
        const rid = Number(cancel[1]);
        const idx = state.admin.queue.findIndex((q) => q.id === rid);
        if (idx >= 0) state.admin.queue.splice(idx, 1);
        return makeJsonResponse({ id: rid, cancelled: true });
      }
    }
    if (pathname === '/api/v1/admin/invites') {
      if (method === 'POST') {
        const nextId =
          Math.max(0, ...state.admin.invites.map((i) => i.id || 0), 0) + 1;
        const invite = {
          id: nextId,
          code: `CODE-${nextId}`,
          max_uses: (body && body.max_uses) || 1,
          expires_at: '2026-12-01T00:00:00Z',
        };
        state.admin.invites.unshift({
          id: nextId,
          max_uses: invite.max_uses,
          use_count: 0,
          expires_at: invite.expires_at,
          expired: false,
          exhausted: false,
          created_at: '2026-11-08T00:00:00Z',
        });
        return makeJsonResponse(invite);
      }
      if (method === 'GET') {
        return makeJsonResponse({ items: clone(state.admin.invites) });
      }
    }
    if (pathname === '/api/v1/admin/audit' && method === 'GET') {
      let items = clone(state.admin.audit);
      if (searchParams.action) {
        const needle = String(searchParams.action).toLowerCase();
        items = items.filter((e) =>
          String(e.action || '').toLowerCase().includes(needle)
        );
      }
      const limit = Math.max(1, Math.min(Number(searchParams.limit) || 100, 500));
      const offset = Math.max(0, Number(searchParams.offset) || 0);
      return makeJsonResponse({
        items: items.slice(offset, offset + limit),
        limit,
        offset,
      });
    }

    return makeErrorResponse(404, `No fake handler for ${method} ${pathname}`);
  };

  global.fetch = fakeFetch;

  return {
    state,
    calls,
    restore() {
      global.fetch = originalFetch;
    },
  };
}

export function renderApp({ hash, token, seed } = {}) {
  const backend = installFakeBackend(seed);
  if (typeof hash !== 'undefined') {
    window.location.hash = hash || '';
  } else {
    window.location.hash = '';
  }
  window.localStorage.removeItem('prime_token');
  if (typeof token === 'string' && token) {
    window.localStorage.setItem('prime_token', makeTestToken(token));
  } else if (token === true) {
    window.localStorage.setItem('prime_token', makeTestToken('admin'));
  }
  const view = render(React.createElement(App));
  return { backend, ...view };
}

export function teardownApp(backend) {
  cleanup();
  if (backend && backend.restore) backend.restore();
  try {
    window.localStorage.removeItem('prime_token');
  } catch {
    // jsdom always has localStorage; guard so teardown never throws.
  }
  window.location.hash = '';
}
