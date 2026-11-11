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

function renderNewJob(seed) {
  const app = renderApp({ hash: '#/new-job', token: 'testuser', seed });
  backend = app.backend;
  return app;
}

// A classification model with real parameters (so first the hyperparameter
// section can render) and a test-result bundle (so the Model Intelligence
// panel can render).
function newJobSeed(extra) {
  return {
    models: [
      {
        name: 'Random_Forest',
        category: 'classification',
        description: 'Random Forest classifier for tabular data.',
        parameters: { n_estimators: 100, max_depth: null, criterion: 'gini' },
        optimization: ['F1', 'Log Loss'],
        test_results: {
          expected_accuracy: [0.8, 0.95],
          best_for: ['tabular_classification'],
          typical_training_time_sec: 7,
          scalability: 'high',
        },
      },
    ],
    ...(extra || {}),
  };
}

async function selectModel(name) {
  const modelSelect = await screen.findByLabelText(/model selection/i);
  fireEvent.change(modelSelect, { target: { value: name } });
}

describe('newjob: renders the sections and keeps submit disabled until a model is chosen', () => {
  it('shows the New run heading, Data and configuration sections, and a disabled Start run', async () => {
    renderNewJob(newJobSeed());

    expect(await screen.findByRole('heading', { name: /^new run$/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /^data$/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /architecture & training configuration/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^start run$/i })).toBeDisabled();
    expect(document.querySelector('.newjob-page')).not.toBeNull();
    expect(document.querySelector('.newjob-form')).not.toBeNull();
  });
});

describe('newjob: every single-control label is associated with its control (htmlFor/id)', () => {
  it('resolves each label text to its control via getByLabelText', async () => {
    renderNewJob(newJobSeed());
    await selectModel('Random_Forest');

    // Static single-control labels (text preserved verbatim from the old UI).
    expect(await screen.findByLabelText(/select local dataset/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/target \/ label column/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/test size split/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/random state/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/task type \(tabular models\)/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/cross-validation folds/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/model selection/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/training mode/i)).toBeInTheDocument();
    // The file input is labelled too.
    expect(screen.getByLabelText(/upload a csv file/i)).toBeInTheDocument();

    // Each label actually points at the control (htmlFor/id association, not nesting).
    const datasetLabel = screen.getByText('Select Local Dataset');
    expect(datasetLabel.tagName).toBe('LABEL');
    expect(datasetLabel).toHaveAttribute('for', 'newjob-dataset');
    expect(document.getElementById('newjob-dataset')).not.toBeNull();
    const modelLabel = screen.getByText('Model Selection');
    expect(modelLabel).toHaveAttribute('for', 'newjob-model');
    expect(document.getElementById('newjob-model')).not.toBeNull();
  });
});

describe('newjob: preset cards share one group label and mark the chosen card', () => {
  it('groups the presets under "Training Preset" and exposes aria-pressed on the cards', async () => {
    renderNewJob(newJobSeed());

    const group = await screen.findByRole('group', { name: /training preset/i });
    expect(group).toBeInTheDocument();
    expect(document.querySelector('.newjob-preset-grid')).not.toBeNull();

    // The default preset is balanced.
    const balanced = screen.getByRole('button', { name: /balanced/i });
    expect(balanced).toHaveAttribute('aria-pressed', 'true');
    expect(balanced.className).toContain('newjob-preset-card');
    const conservative = screen.getByRole('button', { name: /conservative/i });
    expect(conservative).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(conservative);
    expect(conservative).toHaveAttribute('aria-pressed', 'true');
    expect(balanced).toHaveAttribute('aria-pressed', 'false');
  });
});

describe('newjob: hyperparameter fields are labelled by key', () => {
  it('associates the "n_estimators" label with its input once a model is chosen', async () => {
    renderNewJob(newJobSeed());
    await selectModel('Random_Forest');

    const input = await screen.findByLabelText('n_estimators');
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute('id', 'newjob-param-n_estimators');
    expect(screen.getByLabelText('max_depth')).toBeInTheDocument();
    expect(screen.getByLabelText('criterion')).toBeInTheDocument();
  });
});

describe('newjob: the Hugging Face source exposes a labelled URL field', () => {
  it('shows the labelled URL input after switching the source', async () => {
    renderNewJob(newJobSeed());
    await screen.findByRole('button', { name: /hugging face hub/i });

    fireEvent.click(screen.getByRole('button', { name: /hugging face hub/i }));
    const input = await screen.findByLabelText(/hugging face url/i);
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute('id', 'newjob-hf-url');
  });
});

describe('newjob: Model Intelligence panel uses the shared layout classes', () => {
  it('renders the intelligence panel with .newjob-intelligence after the model details load', async () => {
    renderNewJob(newJobSeed());
    await selectModel('Random_Forest');

    expect(await screen.findByText(/model intelligence/i)).toBeInTheDocument();
    expect(document.querySelector('.newjob-intelligence')).not.toBeNull();
    expect(document.querySelector('.newjob-intelligence-grid')).not.toBeNull();
    expect(screen.getByText(/expected accuracy/i)).toBeInTheDocument();
  });
});

describe('newjob: submit behaviour is preserved (guard + successful train)', () => {
  it('blocks a model-only submission with the dataset guard and never calls /train', async () => {
    renderNewJob(newJobSeed());
    await selectModel('Random_Forest');

    // Submit through the form directly: the dataset <select required> would
    // block a button click at the browser-constraint stage, so this reaches
    // handleSubmit's own dataset guard (the path taken when required is off).
    fireEvent.submit(document.querySelector('form'));

    expect(
      await screen.findByText('Select a dataset before starting the run.')
    ).toBeInTheDocument();
    expect(
      backend.calls.some(
        (c) => c.method === 'POST' && c.pathname === '/api/v1/ml/train'
      )
    ).toBe(false);
  });

  it('posts the train payload and navigates to the run details page', async () => {
    renderNewJob(newJobSeed());
    const modelSelect = await screen.findByLabelText(/model selection/i);
    fireEvent.change(modelSelect, { target: { value: 'Random_Forest' } });
    const datasetSelect = await screen.findByLabelText(/select local dataset/i);
    fireEvent.change(datasetSelect, { target: { value: '1' } });

    fireEvent.click(screen.getByRole('button', { name: /^start run$/i }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#/run-details/1');
    });
    const trainCall = backend.calls.find(
      (c) => c.method === 'POST' && c.pathname === '/api/v1/ml/train'
    );
    expect(trainCall).toBeTruthy();
    expect(trainCall.body.model_name).toBe('Random_Forest');
    expect(trainCall.body.dataset_id).toBe(1);
    // Client-side metric selection: classification is optimized/measured by accuracy.
    expect(trainCall.body.optimize_metric).toBe('accuracy');
  });
});

// Phase D1: RL env-id label + submit payload. Per-test seed only -- the
// shared newJobSeed default is untouched so the suite above keeps passing.
// Catalog source of truth: backend/app/model_training.py "Q-Learning"
// (category "reinforcement-learning"); helpers.jsx model-details returns the
// seeded model verbatim, so no helper change is needed. Verified submit
// path: handleSubmit guards dataset with isReinforcementLearning
// (frontend/views/NewJob.jsx `if (!isReinforcementLearning && !payload.dataset_id)`),
// so an RL run submits without a dataset and still carries env_id.
describe('newjob: reinforcement-learning env-id field', () => {
  function rlSeed() {
    return {
      models: [
        {
          name: 'Random_Forest',
          category: 'classification',
          description: 'Random Forest classifier for tabular data.',
          parameters: { n_estimators: 100, max_depth: null, criterion: 'gini' },
          optimization: ['F1', 'Log Loss'],
          test_results: {
            expected_accuracy: [0.8, 0.95],
            best_for: ['tabular_classification'],
            typical_training_time_sec: 7,
            scalability: 'high',
          },
        },
        {
          name: 'Q-Learning',
          category: 'reinforcement-learning',
          description: 'Tabular Q-learning for Gymnasium environments.',
          parameters: {},
          optimization: [],
          test_results: null,
        },
      ],
    };
  }

  it('shows the Gymnasium Environment ID field when Q-Learning is selected and relaxes the dataset requirement', async () => {
    renderNewJob(rlSeed());
    await selectModel('Q-Learning');

    const envInput = await screen.findByLabelText(/gymnasium environment id/i);
    expect(envInput).toBeInTheDocument();
    expect(envInput).toHaveAttribute('id', 'newjob-env-id');

    const datasetSelect = screen.getByLabelText(/select local dataset/i);
    expect(datasetSelect).not.toBeRequired();
    expect(
      screen.getByText(/not required for reinforcement learning/i)
    ).toBeInTheDocument();
  });

  it('posts env_id in the train payload when submitting an RL run (no dataset needed)', async () => {
    renderNewJob(rlSeed());
    await selectModel('Q-Learning');

    const envInput = await screen.findByLabelText(/gymnasium environment id/i);
    fireEvent.change(envInput, { target: { value: 'CartPole-v1' } });

    // RL runs submit without a dataset: handleSubmit's dataset guard is
    // skipped for reinforcement-learning, so click Start directly.
    fireEvent.click(screen.getByRole('button', { name: /^start run$/i }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#/run-details/1');
    });
    const trainCall = backend.calls.find(
      (c) => c.method === 'POST' && c.pathname === '/api/v1/ml/train'
    );
    expect(trainCall).toBeTruthy();
    expect(trainCall.body.model_name).toBe('Q-Learning');
    expect(trainCall.body.env_id).toBe('CartPole-v1');
  });

  it('shows no env-id field for a non-RL model', async () => {
    renderNewJob(rlSeed());
    await selectModel('Random_Forest');

    // Wait for the model-details round trip to settle before asserting absence.
    await screen.findByText(/model intelligence/i);
    expect(
      screen.queryByLabelText(/gymnasium environment id/i)
    ).toBeNull();
  });
});
