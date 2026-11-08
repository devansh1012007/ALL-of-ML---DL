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

describe('static guard: no layout negative margins (R1)', () => {
  // Negative-margin utilities on any side (-m-*, -mt-*, -mx-*, ...). The
  // ResultLine ticks are centered with -translate-x-1/2 / -translate-y-1/2,
  // which are transforms, not layout margins: strip that allow-list before
  // scanning so every other negative margin fails the suite.
  const layoutNegativeMargin = /-m[trblxyse]?-\d/g;
  const stripAllowList = (s) => s.replaceAll('-translate-x-1/2', '').replaceAll('-translate-y-1/2', '');

  it('App.jsx has no layout negative margins (translate allow-list excepted)', () => {
    const withoutAllowList = stripAllowList(appSource);
    expect(withoutAllowList.match(layoutNegativeMargin) || []).toEqual([]);
  });

  it('AdminScreen.jsx has no layout negative margins', () => {
    const withoutAllowList = stripAllowList(source);
    expect(withoutAllowList.match(layoutNegativeMargin) || []).toEqual([]);
  });

  it('the ResultLine translate allow-list is the only intended translate', () => {
    // Pinned so the allow-list stays visible: if these move, the strip above
    // must be re-checked (R3 may redesign the ticks).
    expect(appSource).toContain('-translate-x-1/2');
    expect(appSource).toContain('-translate-y-1/2');
  });
});
