import { describe, it, expect, vi, afterEach } from 'vitest';

// SPEC blocker B1: the frontend must be able to point at an API other than
// localhost. API_BASE is read at build time from VITE_API_BASE, with
// http://localhost:8010 as the default. The value is computed when the module
// is loaded, so every case re-imports the module (resetModules) after setting
// the environment it should see.
const loadApiBase = async () => {
  vi.resetModules();
  const mod = await import('../components/shared.jsx');
  return mod.API_BASE;
};

describe('API_BASE configuration (B1)', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('defaults to http://localhost:8010 when VITE_API_BASE is not set', async () => {
    vi.stubEnv('VITE_API_BASE', undefined);
    expect(await loadApiBase()).toBe('http://localhost:8010');
  });

  it('uses VITE_API_BASE when it is set at build time', async () => {
    vi.stubEnv('VITE_API_BASE', 'https://api.example.com');
    expect(await loadApiBase()).toBe('https://api.example.com');
  });

  it('treats an empty VITE_API_BASE as unset and keeps the default', async () => {
    vi.stubEnv('VITE_API_BASE', '');
    expect(await loadApiBase()).toBe('http://localhost:8010');
  });
});
