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
  const layoutNegativeMargin = /-m[trblxyse]?-(\d|\[)/g;
  const stripAllowList = (s) => s.replaceAll('-translate-x-1/2', '').replaceAll('-translate-y-1/2', '');

  it('App.jsx has no layout negative margins (translate allow-list excepted)', () => {
    const withoutAllowList = stripAllowList(appSource);
    expect(withoutAllowList.match(layoutNegativeMargin) || []).toEqual([]);
    // Guard self-check: the pattern catches both the numeric (-m-4) and the
    // arbitrary-value (-mt-[5px]) forms; the old /-\d/ form missed the latter.
    expect('-mt-[5px]'.match(layoutNegativeMargin)).toEqual(['-mt-[']);
    expect('-m-4'.match(layoutNegativeMargin)).toEqual(['-m-4']);
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

describe('static guard: R4 Admin shared classes', () => {
  it('AdminScreen inputs use .field, not bespoke bg-raised strings', () => {
    // R4 migration (E1): every bespoke input/select was
    // "bg-raised border border-rule rounded-md px-2 py-1"; the shared
    // .field class (with small w-auto/w-24/w-28 modifiers) replaces it.
    expect(source).not.toContain('bg-raised border border-rule');
    expect(source).not.toContain('bg-accent hover:bg-accent-hover');
    expect(source).toContain('className="field w-auto"');
    expect(source).toContain('className="field"');
    // Guard self-check: the banned substring catches the old input form.
    expect('bg-raised border border-rule rounded-md'.includes('bg-raised border border-rule')).toBe(true);
  });

  it('AdminScreen buttons use shared .btn variants and admin icon buttons', () => {
    expect(source).toContain('btn btn-primary');
    expect(source).toContain('btn btn-quiet');
    expect(source).toContain('btn btn-danger');
    expect(source).toContain('admin-icon-btn');
    // Model icons are unchanged (lucide-react).
    expect(source).toContain('CheckCircle');
    expect(source).toContain('Trash2');
    expect(source).toContain('Copy');
  });

  it('AdminScreen tables use .th/.td, shared wrappers and notices', () => {
    expect(source).toContain('admin-table-wrap');
    expect(source).toContain('className="th"');
    expect(source).toContain('className="td"');
    expect(source).not.toContain('px-4 py-3');
    expect(source).not.toContain('divide-rule');
    expect(source).toContain('notice notice-bad');
    expect(source).toContain('notice notice-ok');
    expect(source).toContain('admin-tab');
    expect(source).toContain('admin-badge');
    expect(source).toContain('admin-usage');
    expect(source).toContain('admin-summary');
  });

  it('R4 admin classes are additive token-only styles with no layout hacks', () => {
    // Shared accessors live in styles.css (tokens only, no ad-hoc hex, no
    // negative margins) so Admin converges on the R1/R2/R3 visual system.
    expect(stylesSource).toContain('.admin-tab');
    expect(stylesSource).toContain('.admin-table-wrap');
    expect(stylesSource).toContain('.admin-badge');
    expect(stylesSource).toContain('.admin-usage');
    expect(stylesSource).toContain('.admin-summary');
    expect(stylesSource).toContain('.admin-icon-btn');
    expect(stylesSource).toContain('.admin-form-label');
    // Mobile tables scroll: the wrapper owns the horizontal scroll.
    expect(stylesSource).toMatch(/\.admin-table-wrap\s*\{[^}]*overflow-x:\s*auto/);
    // Interactive minimum: icon buttons and tabs are at least 24px tall.
    expect(stylesSource).toMatch(/\.admin-icon-btn\s*\{[^}]*min-height:\s*1\.5rem/);
    expect(stylesSource).toMatch(/\.admin-tab\s*\{[^}]*min-height:\s*2rem/);
    // No layout negative margins crept back into AdminScreen.
    const layoutNegativeMargin = /-m[trblxyse]?-(\d|\[)/g;
    const withoutAllowList = source.replaceAll('-translate-x-1/2', '').replaceAll('-translate-y-1/2', '');
    expect(withoutAllowList.match(layoutNegativeMargin) || []).toEqual([]);
  });
});
