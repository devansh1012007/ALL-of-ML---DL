import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, '..', 'AdminScreen.jsx'), 'utf8');
const appSource = readFileSync(join(here, '..', 'App.jsx'), 'utf8');
const stylesSource = readFileSync(join(here, '..', 'styles.css'), 'utf8');

describe('static guard: AdminScreen fetch contract', () => {
  it('contains no response.ok inspection of parsed JSON', () => {
    expect(source).not.toContain('response.ok');
  });

  it('contains no err.detail lookup on thrown errors', () => {
    expect(source).not.toContain('err.detail');
  });
});

describe('static guard: P3 aria-live containers are plain content', () => {
  it('RunEvents log and PredictionResult container have no aria-live', () => {
    // Both live containers are gone; the single role="status" status per view
    // carries the announcement (phase-change / summary only).
    expect(appSource).not.toContain('aria-live');
  });
});

describe('static guard: P3 D1 runs wrapper stays in the page', () => {
  it('runs table wrapper has no negative margin', () => {
    expect(appSource).not.toContain('-mx-3');
    expect(appSource).toContain('runs-table-wrap');
  });

  it('D1 scoped padding rule is present without touching global .th/.td', () => {
    expect(stylesSource).toContain('.runs-table-wrap');
    expect(stylesSource).toContain('@media (max-width: 639px)');
    // Scoped rule only; the global cell rules keep their original padding.
    expect(stylesSource).toContain('.th {');
    expect(stylesSource).toContain('.td {');
  });
});

describe('static guard: P3 D2 disclosures use a scoped inline marker', () => {
  it('three disclosure summaries opt into the inline marker', () => {
    const uses = appSource.match(/disclosure-summary/g) || [];
    expect(uses.length).toBeGreaterThanOrEqual(3);
    expect(appSource).toContain('disclosure-marker');
  });

  it('scoped D2 marker rule is present and the global summary rule is left alone', () => {
    expect(stylesSource).toContain('summary.disclosure-summary');
    expect(stylesSource).toContain('.disclosure-marker');
    expect(stylesSource).toContain("summary::before { content: '+';");
  });
});
