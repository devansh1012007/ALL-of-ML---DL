// Moved verbatim from App.jsx in R6 (Frontend UI redesign); only import/export wiring changed.
import React, { useState, useEffect, useContext } from 'react';
import { AuthContext, humanizeKey, classNames, FALLBACK_TRAINING_MODES, FALLBACK_MODE_DESCRIPTIONS, FALLBACK_TRAINING_PRESETS, FALLBACK_MODELS, COMPARABLE_MODEL_CATEGORIES, datasetOptionLabel, groupModels } from '../components/shared.jsx';

export const NewJob = ({ navigate }) => {
  const { apiFetch } = useContext(AuthContext);
  const [models, setModels] = useState([]);
  const [modelsError, setModelsError] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [datasetsError, setDatasetsError] = useState(null);
  const [modelDetails, setModelDetails] = useState(null);
  const [modelDetailsError, setModelDetailsError] = useState(null);
  const [trainingModes, setTrainingModes] = useState(FALLBACK_TRAINING_MODES);
  const [modeDescriptions, setModeDescriptions] = useState(FALLBACK_MODE_DESCRIPTIONS);
  const [modesError, setModesError] = useState(null);
  const [trainingPresets, setTrainingPresets] = useState(FALLBACK_TRAINING_PRESETS);
  const [presetsError, setPresetsError] = useState(null);
  // Keys the user actually edited - an untouched blank field is omitted from the payload,
  // while a field the user cleared on purpose is sent as an explicit null.
  const [touchedParams, setTouchedParams] = useState({});
  
  const [sourceType, setSourceType] = useState('local');
  const [payload, setPayload] = useState({
    model_name: '',
    dataset_id: null,
    hf_dataset_url: '',
    label_column: 'label',
    test_size: 0.2,
    random_state: 42,
    // '' lets the server guess the task from the label column.
    task_type: '',
    cv_folds: 5,
    mode: 'manual',
    preset: 'balanced',
    env_id: '',
    hyperparameters: {}
  });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  // The state of the upload: the file is sent to the server, which registers
  // it as a dataset of the user.
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [uploadedDataset, setUploadedDataset] = useState(null);

  // The dataset that is selected in the form, and the columns it has: the
  // label column is picked from them, so it does not have to be typed.
  const selectedDataset = datasets.find(d => d.id === payload.dataset_id) || null;
  const labelColumnOptions = selectedDataset
    ? (selectedDataset.columns || []).map(column => column.name)
    : [];

  // The dataset is passed in when it is not in the list yet: after an upload
  // the list is updated in the same event handler, so the closure still holds
  // the old one and the lookup would find nothing.
  // The payload is updated with the functional form, so that a change the
  // user made while the upload was running is not rolled back.
  const selectDataset = (datasetId, knownDataset) => {
    const id = datasetId === '' || datasetId === null ? null : Number(datasetId);
    setPayload(previous => {
      const dataset = knownDataset || datasets.find(d => d.id === id);
      const columns = dataset ? (dataset.columns || []).map(column => column.name) : [];
      return {
        ...previous,
        dataset_id: id,
        // The registry suggests the label column; it is only used when the
        // suggestion is one of the columns of the file.
        label_column: dataset && dataset.label_column && columns.includes(dataset.label_column)
          ? dataset.label_column
          : (columns.includes(previous.label_column) ? previous.label_column : (columns[0] || previous.label_column)),
      };
    });
  };

  const handleUpload = async (event) => {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const dataset = await apiFetch('/api/v1/ml/datasets/upload', {
        method: 'POST',
        body: form,
      });
      setUploadedDataset(dataset);
      setDatasets(previous => {
        const without = previous.filter(item => item.id !== dataset.id);
        return [...without, dataset].sort((a, b) => a.name.localeCompare(b.name));
      });
      // The uploaded dataset is passed in: the list above is not updated yet.
      selectDataset(dataset.id, dataset);
    } catch (err) {
      setUploadError(err.message || 'The upload failed.');
    } finally {
      setUploading(false);
      // The input is cleared, so that the same file can be uploaded again.
      event.target.value = '';
    }
  };

  useEffect(() => {
    apiFetch('/api/v1/ml/models')
      .then(data => {
        setModels(Array.isArray(data) ? data : []);
        setModelsError(null);
      })
      // A failed request is not an empty model list: the built-in fallback list
      // keeps the form usable and the reason is reported below the select.
      .catch(err => {
        setModels(FALLBACK_MODELS);
        setModelsError(err.message || 'Unknown error');
      });
    apiFetch('/api/v1/ml/datasets')
      .then(data => { setDatasets(data?.datasets || []); setDatasetsError(null); })
      // A failed request is not the same as "the server has no datasets": the two
      // cases are reported separately so a backend outage is not mistaken for an
      // empty data directory.
      .catch(err => { setDatasets([]); setDatasetsError(err.message || 'Unknown error'); });
    apiFetch('/api/v1/ml/training-modes')
      .then(data => {
        if (Array.isArray(data?.modes) && data.modes.length > 0) setTrainingModes(data.modes);
        if (data?.descriptions && typeof data.descriptions === 'object') {
          setModeDescriptions({ ...FALLBACK_MODE_DESCRIPTIONS, ...data.descriptions });
        }
        setModesError(null);
      })
      // The form stays usable through the built-in fallback list, but the reason
      // is reported instead of being swallowed.
      .catch(err => { setModesError(err.message || 'Unknown error'); });
    apiFetch('/api/v1/ml/training-presets')
      .then(data => {
        setTrainingPresets(Array.isArray(data?.presets) ? data.presets : []);
        setPresetsError(null);
      })
      // The presets keep the form usable through the built-in fallback list and
      // the reason is reported below the preset buttons.
      .catch(err => {
        setTrainingPresets(FALLBACK_TRAINING_PRESETS);
        setPresetsError(err.message || 'Unknown error');
      });
  }, [apiFetch]);

  const selectedModelDef = models.find(m => m.name === payload.model_name);
  const isReinforcementLearning = selectedModelDef?.category === 'reinforcement-learning';
  const presetInfo = trainingPresets.find(p => p.name === payload.preset);
  // The mode description is the text the backend sends; the local copy is only
  // the fallback for an unreachable backend.
  const modeDescription = modeDescriptions[payload.mode]
    || FALLBACK_MODE_DESCRIPTIONS[payload.mode]
    || 'Parameters are configured automatically for this training mode.';
  const modeOptions = trainingModes.includes(payload.mode)
    ? trainingModes
    : [...trainingModes, payload.mode];
  // auto_search trains every candidate the client sends and keeps the best one, so
  // the client has to provide the candidate list. Only models of the same category
  // solve the same task and report comparable metrics, so the pool is the catalog
  // slice that shares the selected model's category. The estimator-backed
  // categories are the ones the backend can score against each other (the
  // transformer and vision models are not).
  const searchCandidates = selectedModelDef
    ? models
        .filter(m => m.category === selectedModelDef.category && COMPARABLE_MODEL_CATEGORIES.includes(m.category))
        .map(m => m.name)
    : [];

  // Fetch full model details when model changes
  useEffect(() => {
    if (payload.model_name) {
      // The previous model's details are dropped first: they must not be shown
      // next to the newly selected model while the request is in flight.
      setModelDetails(null);
      setModelDetailsError(null);
      apiFetch(`/api/v1/ml/model-details?model_name=${encodeURIComponent(payload.model_name)}`)
        .then(data => { setModelDetails(data); setModelDetailsError(null); })
        // A failed request is reported in place of the Model Intelligence panel
        // instead of leaving it silently missing.
        .catch(err => setModelDetailsError(err.message || 'Unknown error'));
    } else {
      setModelDetails(null);
      setModelDetailsError(null);
    }
  }, [payload.model_name, apiFetch]);

  // Auto-populate parameters when model changes
  useEffect(() => {
    if (!selectedModelDef) return;
    if (payload.mode === 'manual') {
      setPayload(prev => ({ ...prev, hyperparameters: { ...selectedModelDef.parameters } }));
      setTouchedParams({});
    } else {
      // The automatic modes let the backend pick the parameters. Sending the
      // catalog defaults would win the backend's merge (the request is applied
      // last), so the mode's own suggestion would never take effect.
      setPayload(prev => ({ ...prev, hyperparameters: {} }));
      setTouchedParams({});
    }
  }, [payload.model_name, payload.mode, selectedModelDef]);

  const handleParamChange = (key, value) => {
    setTouchedParams(prev => ({ ...prev, [key]: true }));
    setPayload(prev => ({
      ...prev,
      hyperparameters: { ...prev.hyperparameters, [key]: value }
    }));
  };

  // Builds the hyperparameters actually sent to the backend:
  // numeric catalog values stay numeric, blank untouched fields are omitted and a
  // field the user cleared is only sent as an explicit null when the estimator
  // accepts it (the catalog default is None).
  // An empty string is never sent for any type: the estimators reject it
  // (LogisticRegression(penalty="") -> 400, LinearRegression(fit_intercept="") ->
  // InvalidParameterError), so a cleared non-numeric field is dropped instead so
  // the catalog default applies.
  const buildHyperparameters = () => {
    const catalog = selectedModelDef?.parameters || {};
    const result = {};
    Object.entries(payload.hyperparameters).forEach(([key, val]) => {
      const definition = catalog[key];
      const isNumeric = typeof definition === 'number' || definition === null;
      const isBoolean = typeof definition === 'boolean';
      const raw = (val === null || val === undefined) ? '' : String(val).trim();
      if (raw === '') {
        // A cleared numeric field: an optional parameter (the catalog default is
        // None, e.g. max_depth) already accepts None there, so the cleared field is
        // sent as an explicit null. A parameter with a numeric default does not
        // accept None (LogisticRegression(C=None) is rejected), so its key is
        // dropped and the catalog default applies instead.
        if (isNumeric && touchedParams[key] && definition === null) result[key] = null;
        return;
      }
      if (isBoolean) {
        // A boolean parameter is edited in a text field, so the typed text is
        // converted back to a boolean - the estimator rejects the string "true".
        const lowered = raw.toLowerCase();
        if (lowered === 'true' || lowered === 'false') result[key] = lowered === 'true';
        return;
      }
      if (!isNumeric) {
        // A string parameter (an enum or a path): the trimmed text is sent.
        result[key] = raw;
        return;
      }
      const parsed = Number(raw);
      // A number input reports an empty string for invalid text, so a value that
      // is not a number is a safety net: the key is dropped and the catalog
      // default applies.
      if (Number.isFinite(parsed)) result[key] = parsed;
    });
    return result;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    // The backend rejects a run without a data source with a generic 400, so
    // the missing input is reported here instead of leaving the user with
    // that message.
    if (sourceType === 'local') {
      if (!isReinforcementLearning && !payload.dataset_id) {
        setError('Select a dataset before starting the run.');
        return;
      }
    } else if (!payload.hf_dataset_url) {
      setError('Enter a Hugging Face dataset URL or path before starting the run.');
      return;
    }

    setSubmitting(true);

    try {
      const submitPayload = { ...payload };
      if (sourceType === 'local') delete submitPayload.hf_dataset_url;
      if (sourceType === 'hf') delete submitPayload.dataset_id;
      submitPayload.hyperparameters = buildHyperparameters();
      // The metric the run is optimized for follows the task of the selected
      // model: a regression model is scored with r2, every other task with
      // accuracy. Without this every run would be recorded as an accuracy run,
      // which is wrong for a regression model.
      submitPayload.optimize_metric = selectedModelDef?.category === 'regression' ? 'r2' : 'accuracy';
      // Empty values are not valid for the backend: a null dataset id would be
      // stored as a "huggingface" run and an empty env id as "".
      if (!submitPayload.dataset_id) delete submitPayload.dataset_id;
      if (!submitPayload.hf_dataset_url) delete submitPayload.hf_dataset_url;
      if (!submitPayload.env_id) delete submitPayload.env_id;
      // auto_search needs the candidate list, otherwise the backend trains the
      // selected model alone and the mode does nothing.
      if (payload.mode === 'auto_search' && payload.model_name) {
        submitPayload.model_candidates = searchCandidates.length > 0
          ? searchCandidates
          : [payload.model_name];
      }

      // Ensure types are correct for numbers
      submitPayload.test_size = parseFloat(submitPayload.test_size);
      submitPayload.random_state = parseInt(submitPayload.random_state, 10);
      if (!submitPayload.task_type) delete submitPayload.task_type;
      submitPayload.cv_folds = parseInt(submitPayload.cv_folds, 10);
      
      // The training runs in the background: the answer carries the id of the
      // run and nothing else. The metrics are written in the run itself, so
      // the details view is the place to watch them.
      const result = await apiFetch('/api/v1/ml/train', {
        method: 'POST',
        body: JSON.stringify(submitPayload)
      });
      navigate('run-details', result.run_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const formatTestResults = () => {
    if (!modelDetails?.test_results) return null;
    const tr = modelDetails.test_results;
    
    return {
      accuracy: tr.expected_accuracy || tr.expected_r2 || tr.expected_reward || tr.expected_silhouette,
      accuracyLabel: tr.expected_accuracy ? 'Expected Accuracy' : 
                      tr.expected_r2 ? 'Expected R²' : 
                      tr.expected_reward ? 'Expected Reward' : 
                      'Expected Silhouette',
      bestFor: tr.best_for,
      trainingTime: tr.typical_training_time_sec,
      scalability: tr.scalability,
    };
  };

  const testResults = formatTestResults();

  // INVARIANT: control ids are stable and unique within the single NewJob
  // form mount; each visible label's htmlFor resolves to its control so
  // getByLabelText and click-to-focus keep working after the class restyle.
  return (
    <div className="newjob-page max-w-6xl">
      <header className="page-header">
        <div>
          <h1 className="mb-1">New run</h1>
          <p className="text-muted">Choose the data, the model, and how it should be trained.</p>
        </div>
      </header>

      {error && (
        <div role="alert" className="notice notice-bad">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="newjob-form">

        {/* Section A: Data */}
        <div className="panel">
          <h2 className="newjob-section-title">Data</h2>

          <div className="newjob-mode-toggle" role="group" aria-label="Dataset source">
            <button
              type="button"
              onClick={() => setSourceType('local')}
              aria-pressed={sourceType === 'local'}
              className="newjob-mode-btn"
            >
              Local Dataset (CSV)
            </button>
            <button
              type="button"
              onClick={() => setSourceType('hf')}
              aria-pressed={sourceType === 'hf'}
              className="newjob-mode-btn"
            >
              Hugging Face Hub
            </button>
          </div>

          <div className="newjob-grid-2">
            {sourceType === 'local' ? (
              <div>
                <label htmlFor="newjob-dataset" className="newjob-field-label">Select Local Dataset</label>
                {/* The select stays mounted when the list is empty so the "required"
                    rule keeps blocking the submission instead of posting an empty
                    dataset name to the backend. */}
                <select
                  id="newjob-dataset"
                  required={!isReinforcementLearning}
                  value={payload.dataset_id ?? ''}
                  onChange={(e) => selectDataset(e.target.value)}
                  className="field"
                >
                  {datasets.length === 0 && (
                    <option value="" disabled>-- no datasets available --</option>
                  )}
                  {datasets.length > 0 && (
                    <option value="">-- Select --</option>
                  )}
                  {datasets.map(d => <option key={d.id} value={d.id}>{datasetOptionLabel(d)}</option>)}
                </select>
                {datasetsError && (
                  <p className="notice mt-2">
                    Could not load datasets: {datasetsError}
                  </p>
                )}
                {!datasetsError && datasets.length === 0 && (
                  <p className="newjob-hint">
                    No datasets available. Upload a CSV file below to start.
                  </p>
                )}
                {isReinforcementLearning && (
                  <p className="newjob-hint">Not required for reinforcement learning models.</p>
                )}
                {selectedDataset && selectedDataset.columns && selectedDataset.columns.length > 0 && (
                  <p className="newjob-hint">
                    {selectedDataset.row_count} rows, {selectedDataset.columns.length} columns
                    {selectedDataset.source === 'builtin' ? ', shipped with the repository' : ', uploaded by you'}
                  </p>
                )}
                {!isReinforcementLearning && (
                  <div className="mt-3">
                    <label htmlFor="newjob-upload" className="newjob-field-label-small">Upload a CSV file</label>
                    <div className="newjob-upload-row">
                      <input
                        id="newjob-upload"
                        type="file"
                        accept=".csv,text/csv"
                        onChange={handleUpload}
                        disabled={uploading}
                        className="text-sm text-muted file:mr-3 file:rounded-md file:border-0 file:bg-raised file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-ink hover:file:bg-rule disabled:opacity-50"
                      />
                      {uploading && <span role="status" className="text-sm text-muted">Uploading...</span>}
                    </div>
                    {uploadError && (
                      <p className="notice mt-2">
                        {uploadError}
                      </p>
                    )}
                    {uploadedDataset && (
                      <p className="notice mt-2">
                        Uploaded “{uploadedDataset.name}” with {uploadedDataset.row_count} rows. It is selected above.
                      </p>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="md:col-span-2">
                <label htmlFor="newjob-hf-url" className="newjob-field-label">Hugging Face URL / Path</label>
                <input
                  id="newjob-hf-url"
                  type="text"
                  required
                  placeholder="e.g., databricks/databricks-dolly-15k"
                  value={payload.hf_dataset_url}
                  onChange={(e) => setPayload({...payload, hf_dataset_url: e.target.value})}
                  className="field"
                />
              </div>
            )}

            <div>
              {/* The select/input share one id: only one mounts at a time. */}
              <label htmlFor="newjob-label-column" className="newjob-field-label">Target / Label Column</label>
              {labelColumnOptions.length > 0 ? (
                <select
                  id="newjob-label-column"
                  required
                  value={payload.label_column}
                  onChange={(e) => setPayload({...payload, label_column: e.target.value})}
                  className="field"
                >
                  {labelColumnOptions.map(name => <option key={name} value={name}>{name}</option>)}
                </select>
              ) : (
                <input
                  id="newjob-label-column"
                  type="text"
                  required
                  placeholder="label"
                  value={payload.label_column}
                  onChange={(e) => setPayload({...payload, label_column: e.target.value})}
                  className="field"
                />
              )}
              {labelColumnOptions.length > 0 && (
                <p className="newjob-hint">The columns of the selected dataset.</p>
              )}
            </div>

            <div className="newjob-pair">
               <div>
                <label htmlFor="newjob-test-size" className="newjob-field-label">Test Size Split</label>
                <input
                  id="newjob-test-size"
                  type="number" 
                  step="0.01" min="0.01" max="0.99" required
                  value={payload.test_size}
                  onChange={(e) => setPayload({...payload, test_size: e.target.value})}
                  className="field"
                />
              </div>
               <div>
                <label htmlFor="newjob-random-state" className="newjob-field-label">Random State</label>
                <input 
                  id="newjob-random-state"
                  type="number" 
                  required
                  value={payload.random_state}
                  onChange={(e) => setPayload({...payload, random_state: e.target.value})}
                  className="field"
                />
              </div>
            </div>

            <div className="newjob-pair">
              <div>
                <label htmlFor="newjob-task-type" className="newjob-field-label">Task type (tabular models)</label>
                <select
                  id="newjob-task-type"
                  value={payload.task_type}
                  onChange={(e) => setPayload({...payload, task_type: e.target.value})}
                  className="field"
                >
                  <option value="">Guess from the label column</option>
                  <option value="classification">Classification</option>
                  <option value="regression">Regression</option>
                </select>
              </div>
              <div>
                <label htmlFor="newjob-cv-folds" className="newjob-field-label">Cross-validation folds (0 = off)</label>
                <input
                  id="newjob-cv-folds"
                  type="number" min="0" max="20" required
                  value={payload.cv_folds}
                  onChange={(e) => setPayload({...payload, cv_folds: e.target.value})}
                  className="field"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Section B: Model & Mode Selection */}
        <div className="panel">
           <h2 className="newjob-section-title">Architecture & Training Configuration</h2>

           <div className="newjob-grid-2 mb-6">
             <div>
                <label htmlFor="newjob-model" className="newjob-field-label">Model Selection</label>
                 <select
                   id="newjob-model"
                   required
                   value={payload.model_name}
                   onChange={(e) => setPayload({...payload, model_name: e.target.value})}
                   className="field"
                 >
                   <option value="">Choose a model</option>
                   {groupModels(models).map(([label, rows]) => (
                     <optgroup key={label} label={label}>
                       {rows.map((m) => {
                         const usable = m.implemented !== false && m.available !== false;
                         return (
                           <option key={m.name} value={m.name} disabled={!usable}>
                             {m.name}{usable ? '' : (m.implemented === false ? ' (not implemented)' : ' (not available here)')}
                           </option>
                         );
                       })}
                     </optgroup>
                   ))}
                 </select>
                 {modelsError && (
                   <p className="notice mt-2">
                     Could not load models — {modelsError}. Using the built-in fallback list.
                   </p>
                 )}
                 <p className="newjob-hint">
                   {(() => {
                     const chosen = models.find((m) => m.name === payload.model_name);
                     return chosen && chosen.description ? chosen.description : 'Greyed-out models cannot run on this server; the Models page says why.';
                   })()}
                 </p>
               </div>

             <div>
               <label htmlFor="newjob-mode" className="newjob-field-label">Training Mode</label>
               <select
                 id="newjob-mode"
                 value={payload.mode}
                 onChange={(e) => setPayload({...payload, mode: e.target.value})}
                 className="field"
               >
                 {modeOptions.map(m => <option key={m} value={m}>{humanizeKey(m)}</option>)}
               </select>
               {modesError && (
                 <p className="text-xs text-warn/90 border border-warn/40 rounded-md px-3 py-2 mt-2">
                   Could not load the training modes — {modesError}. Using the built-in fallback list.
                 </p>
               )}
             </div>
           </div>

            {/* Mode Description */}
            {payload.mode !== 'manual' && (
              <div className="newjob-mode-note">
                <div className="text-sm text-accent">
                  <span className="font-semibold">Mode: {humanizeKey(payload.mode)}</span> - 
                  {modeDescription}
                </div>
              </div>
            )}

           {/* Preset Selector. // DECISION: a preset is a group of toggle
               buttons, so the title is a group label (aria-labelledby) rather
               than a <label htmlFor> (which needs one labelable control).
               Text is verbatim; selection is exposed via aria-pressed. */}
           <div className="mb-6" role="group" aria-labelledby="newjob-preset-label">
             <span id="newjob-preset-label" className="newjob-field-label">Training Preset</span>
             <div className="newjob-preset-grid">
               {trainingPresets.map(p => (
                 <button
                   key={p.name}
                   type="button"
                   onClick={() => setPayload({...payload, preset: p.name})}
                   aria-pressed={payload.preset === p.name}
                   className="newjob-preset-card"
                 >
                    <div className="newjob-preset-name">{p.name}</div>
                    <div className="newjob-preset-desc">{p.description}</div>
                  </button>
                ))}
              </div>
              {presetsError && (
                <p className="notice mt-2">
                  Could not load training presets — {presetsError}. Using the built-in fallback list.
                </p>
              )}
            </div>

           {selectedModelDef?.category === 'reinforcement-learning' && (
             <div className="mb-6">
                <label htmlFor="newjob-env-id" className="newjob-field-label">Gymnasium Environment ID (Required for RL)</label>
                <input
                  id="newjob-env-id"
                  type="text" 
                  required
                  placeholder="e.g., CartPole-v1"
                  value={payload.env_id}
                  onChange={(e) => setPayload({...payload, env_id: e.target.value})}
                  className="field"
                />
             </div>
           )}
        </div>

        {/* Section C: Model Details Panel */}
        {modelDetails && testResults && (
          <div className="newjob-intelligence">
            <h3 className="text-lg font-semibold text-strong mb-4">📊 Model Intelligence</h3>
            <div className="newjob-intelligence-grid">
              <div className="newjob-intelligence-cell">
                <div className="text-xs text-muted mb-2">{testResults.accuracyLabel}</div>
                <div className="text-lg font-bold text-accent">
                  {testResults.accuracy ? `${(testResults.accuracy[0]*100).toFixed(0)}% - ${(testResults.accuracy[1]*100).toFixed(0)}%` : 'N/A'}
                </div>
              </div>

              <div className="newjob-intelligence-cell">
                <div className="text-xs text-muted mb-2">Training Time</div>
                <div className="text-lg font-bold text-ok">~{testResults.trainingTime}s</div>
              </div>

              <div className="newjob-intelligence-cell">
                <div className="text-xs text-muted mb-2">Scalability</div>
                <div className={classNames("text-lg font-bold", 
                  testResults.scalability === 'high' ? 'text-ok' :
                  testResults.scalability === 'medium' ? 'text-warn' : 'text-warn'
                )}>
                  {testResults.scalability?.charAt(0).toUpperCase() + testResults.scalability?.slice(1)}
                </div>
              </div>

              <div className="newjob-intelligence-cell">
                <div className="text-xs text-muted mb-2">Optimization Targets</div>
                <div className="text-sm text-ink">
                  {selectedModelDef?.optimization?.length > 0 ? selectedModelDef.optimization.slice(0, 2).join(', ') : 'N/A'}
                  {selectedModelDef?.optimization?.length > 2 && '...'}
                </div>
              </div>
            </div>

            {testResults.bestFor && (
              <div className="mt-4 pt-4 border-t border-rule/50">
                <div className="text-xs text-muted mb-2">Best For:</div>
                <div className="flex flex-wrap gap-2">
                  {testResults.bestFor.map((tag, idx) => (
                    <span key={idx} className="newjob-tag">
                      {tag.replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* The Model Intelligence panel is replaced by the reason it could not be
            loaded, so the section never disappears without an explanation. */}
        {modelDetailsError && (
          <div className="notice text-sm">
            Could not load model details — {modelDetailsError}.
          </div>
        )}

        {/* Section D: Hyperparameters */}
        {selectedModelDef && payload.mode === 'manual' && (
          <div className="panel">
             <h2 className="newjob-section-title">Hyperparameters</h2>

             {Object.keys(payload.hyperparameters).length > 0 ? (
              <div className="newjob-params-grid">
                {Object.entries(payload.hyperparameters).map(([key, val]) => {
                  const definition = selectedModelDef?.parameters?.[key];
                  // A null catalog default is an optional numeric parameter (e.g. max_depth).
                  const isNumeric = typeof definition === 'number' || definition === null;
                  // The catalog cannot tell an integer default from a float one (JSON
                  // turns 1.0 into 1), so every numeric input accepts any value:
                  // step="1" would make C = 0.5 fail the browser's own validation.
                  const step = isNumeric ? 'any' : undefined;
                  // Catalog keys are snake_case identifiers, safe as an id fragment.
                  const paramId = `newjob-param-${key}`;
                  return (
                   <div key={key}>
                    <label htmlFor={paramId} className="newjob-field-label-small tabular-nums">{key}</label>
                    <input
                       id={paramId}
                       type={isNumeric ? 'number' : 'text'}
                       step={step}
                       value={val === null || val === undefined ? '' : val}
                       onChange={(e) => handleParamChange(key, e.target.value)}
                       className="field"
                    />
                   </div>
                  );
                })}
              </div>
             ) : (
              <div className="text-sm text-faint italic">No configurable parameters required or auto-adjusted mode selected.</div>
             )}
          </div>
        )}

        {selectedModelDef && payload.mode !== 'manual' && (
          <div className="panel">
             <h2 className="newjob-section-title">Hyperparameters</h2>
             <div className="text-sm text-muted">
               <p className="mb-2">
                  In <span className="font-semibold">{humanizeKey(payload.mode)}</span> mode, hyperparameters will be automatically {
                    payload.mode === 'auto_tune' ? 'tuned via randomized search' :
                    payload.mode === 'auto_fine_tune' ? 'tuned around the current configuration' :
                    payload.mode === 'llm_fine_tune' ? 'suggested by Google Gemini' :
                    payload.mode === 'auto_search' ? 'model selection across candidates' : 'configured'
                  }.
               </p>
               {payload.mode === 'auto_search' && (
                 <p className="mb-2">
                   {searchCandidates.length > 0 ? (
                     <>
                       Compared models: <span className="tabular-nums text-ink">{searchCandidates.join(', ')}</span>
                     </>
                   ) : (
                     <>
                       No comparable candidate for {selectedModelDef.name} - it is trained on its own.
                     </>
                   )}
                 </p>
               )}
               <p>
                 {presetInfo && (
                   <>
                     <span className="font-semibold">Preset "{presetInfo.name}":</span> {presetInfo.description}
                   </>
                 )}
               </p>
             </div>
          </div>
        )}

        <div className="newjob-submit-row">
          {!payload.model_name && <p className="text-sm text-faint">Choose a model to continue.</p>}
          <button type="submit" disabled={submitting || !payload.model_name} className="btn btn-primary">
            {submitting ? 'Queueing...' : 'Start run'}
          </button>
        </div>
      </form>
    </div>
  );
};
