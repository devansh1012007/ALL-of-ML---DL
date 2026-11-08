// Moved verbatim from App.jsx in R6 (Frontend UI redesign); only import/export wiring changed.
import React, { useState, useContext } from 'react';
import { AuthContext } from '../components/shared.jsx';
import { ThemeToggle } from '../components/theme.jsx';

export const AuthView = ({ mode, setMode, theme, onToggleTheme }) => {
  const { login, apiFetch, sessionNotice } = useContext(AuthContext);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (mode === 'register') {
        await apiFetch('/api/v1/register', {
          method: 'POST',
          body: JSON.stringify({ username, password })
        });
        // Auto-login after register
      }

      const params = new URLSearchParams();
      params.append('username', username);
      params.append('password', password);

      const data = await apiFetch('/token', {
        method: 'POST',
        body: params
      });

      login(data.access_token);
    } catch (err) {
      setError(err.status === 409
        ? 'Username already taken. Please choose a different username.'
        : err.status === 429
        ? 'Too many attempts. Please wait a minute and try again.'
        : err.message);
    } finally {
      setLoading(false);
    }
  };

  const registering = mode === 'register';
  return (
    <main className="min-h-screen flex items-center px-6 py-12">
      <div className="auth-card">
        <p className="auth-brand text-sm font-medium mb-10">PrimeTrade AutoML</p>
        <div className="mb-6">
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
        <h1 className="mb-2">{registering ? 'Create an account' : 'Sign in'}</h1>
        <p className="text-muted mb-8">Train a model on your data, check it against a baseline, and use it.</p>
        {sessionNotice && <p role="status" className="notice mb-5">{sessionNotice}</p>}
        {error && <p role="alert" id="auth-error" className="notice notice-bad mb-5">{error}</p>}
        <form onSubmit={handleSubmit} className="auth-form">
          <div>
            <label htmlFor="auth-username" className="block text-sm text-muted mb-1.5">Username</label>
            <input
              id="auth-username" type="text" required autoComplete="username"
              value={username} onChange={(e) => setUsername(e.target.value)}
              className="field"
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? 'auth-error' : undefined}
            />
          </div>
          <div>
            <label htmlFor="auth-password" className="block text-sm text-muted mb-1.5">Password</label>
            <input
              id="auth-password" type="password" required
              autoComplete={registering ? 'new-password' : 'current-password'}
              minLength={registering ? 8 : undefined}
              value={password} onChange={(e) => setPassword(e.target.value)}
              className="field"
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? 'auth-error' : undefined}
            />
            {registering && <p className="mt-1.5 text-sm text-faint">At least 8 characters.</p>}
          </div>
          <button type="submit" disabled={loading} className="btn btn-primary w-full">
            {loading ? (registering ? 'Creating account...' : 'Signing in...') : (registering ? 'Create account' : 'Sign in')}
          </button>
        </form>
        <p className="mt-8 text-sm text-muted">
          {registering ? 'Already have an account? ' : 'New here? '}
          <button onClick={() => setMode(registering ? 'login' : 'register')} className="link">
            {registering ? 'Sign in' : 'Create an account'}
          </button>
        </p>
      </div>
    </main>
  );
};
