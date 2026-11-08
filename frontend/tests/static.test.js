import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, '..', 'AdminScreen.jsx'), 'utf8');
const appSource = readFileSync(join(here, '..', 'App.jsx'), 'utf8');
const stylesSource = readFileSync(join(here, '..', 'styles.css'), 'utf8');

// R6 split (plan F1): App.jsx shrank to the shell + re-exports and the views
// moved verbatim to views/*.jsx, the shared + metrics pieces to
// components/*.jsx. The guards below read source text, not rendered output,
// so a check that only reads App.jsx silently loses every string that moved
// (disclosure-summary, -mx-3, aria-live, scope="col", ...). Scan the union
// the guards actually protect: App.jsx + views/** + components/**. Admin
// stays out of scope for the move and is already scanned separately above
// as `source`, so the union of `combinedAppSource` and `source` is every
// shipped .jsx the guards cover.
const readJsxFiles = (dir) => {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  return entries
    .sort((a, b) => a.name.localeCompare(b.name))
    .flatMap((entry) => {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) return readJsxFiles(full);
      return entry.isFile() && entry.name.endsWith('.jsx') ? [full] : [];
    });
};

const scannedAppFiles = [
  join(here, '..', 'App.jsx'),
  ...readJsxFiles(join(here, '..', 'views')),
  ...readJsxFiles(join(here, '..', 'components')),
];
const combinedAppSource = scannedAppFiles
  .map((file) => readFileSync(file, 'utf8'))
  .join('\n');

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
    expect(combinedAppSource).not.toContain('aria-live');
  });
});

describe('static guard: P3 D1 runs wrapper stays in the page', () => {
  it('runs table wrapper has no negative margin', () => {
    expect(combinedAppSource).not.toContain('-mx-3');
    expect(combinedAppSource).toContain('runs-table-wrap');
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
    const uses = combinedAppSource.match(/disclosure-summary/g) || [];
    expect(uses.length).toBeGreaterThanOrEqual(3);
    expect(combinedAppSource).toContain('disclosure-marker');
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

  it('App.jsx + views/components have no layout negative margins (translate allow-list excepted)', () => {
    const withoutAllowList = stripAllowList(combinedAppSource);
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
    expect(combinedAppSource).toContain('-translate-x-1/2');
    expect(combinedAppSource).toContain('-translate-y-1/2');
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

describe('static guard: R5 mobile stacking', () => {
  it('.newjob-pair stacks below sm and pairs at sm+', () => {
    // Base rule is a single column; the two-column pair starts at 640px.
    // The old stylesheet kept repeat(2, ...) at every width, so the Test Size /
    // Random State fields were crushed side-by-side at 390px.
    expect(stylesSource).toMatch(/\.newjob-pair\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*;/);
    expect(stylesSource).toMatch(/@media\s*\(min-width:\s*640px\)\s*\{\s*\.newjob-pair\s*\{[^}]*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
    // Self-check: the old always-two-column rule matches the anti-pattern and
    // does NOT match the stacked-base rule above.
    const oldRule = '.newjob-pair { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }';
    expect(/\.newjob-pair\s*\{[^}]*repeat\(2,\s*minmax\(0,\s*1fr\)\)/.test(oldRule)).toBe(true);
    expect(/\.newjob-pair\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*;/.test(oldRule)).toBe(false);
  });

  it('data tables keep a readable min-width and scroll inside their wrappers at 390px', () => {
    // Min-width makes 390px layouts scroll instead of crushing columns;
    // the wrapper owns the horizontal scroll.
    expect(stylesSource).toMatch(/\.runs-table-wrap table\s*\{[^}]*min-width:/);
    expect(stylesSource).toMatch(/\.compare-table-wrap table\s*\{[^}]*min-width:/);
    expect(stylesSource).toMatch(/\.admin-table-wrap table\s*\{[^}]*min-width:/);
    expect(stylesSource).toMatch(/\.admin-table-wrap\s*\{[^}]*overflow-x:\s*auto/);
    expect(stylesSource).toMatch(/\.compare-table-wrap\s*\{[^}]*overflow-x:\s*auto/);
    // The runs wrapper scrolls via its Tailwind overflow-x-auto class.
    expect(combinedAppSource).toContain('overflow-x-auto runs-table-wrap');
  });
});

describe('static guard: R5 touch targets (indicative; manual probe in tech-debt)', () => {
  it('interactive classes declare a 24px floor', () => {
    // A string scan cannot measure rendered height: this pins the declared
    // minima only. The definitive check is the manual 390px probe in tech-debt.
    expect(stylesSource).toMatch(/\.btn\s*\{[^}]*min-height:\s*2rem/);
    expect(stylesSource).toMatch(/\.nav-link\s*\{[^}]*min-height:\s*1\.5rem/);
    expect(stylesSource).toMatch(/\.breadcrumb a\s*\{[^}]*min-height:\s*1\.5rem/);
    expect(stylesSource).toMatch(/\.link\s*\{[^}]*min-height:\s*1\.5rem/);
    expect(stylesSource).toMatch(/\.compare-check\s*\{[^}]*min-height:\s*1\.5rem/);
    expect(stylesSource).toMatch(/summary\.disclosure-summary\s*\{[^}]*min-height:\s*1\.5rem/);
    // Sign-out keeps its 24px Tailwind floor.
    expect(combinedAppSource).toContain('min-h-6');
  });

  it('focus-visible and the field focus ring are declared', () => {
    // Preservation pin (audit): keyboard focus is never colour-only.
    expect(stylesSource).toContain(':focus-visible');
    expect(stylesSource).toMatch(/\.field:focus\s*\{[^}]*box-shadow/);
  });
});

describe('static guard: R5 labels, accessible names, and table scopes', () => {
  it('remaining in-between labels are explicit (compare metric, quota profile)', () => {
    expect(combinedAppSource).toContain('htmlFor="compare-metric"');
    expect(combinedAppSource).toContain('id="compare-metric"');
    expect(source).toContain('htmlFor="quota-profile"');
    expect(source).toContain('id="quota-profile"');
  });

  it('admin icon-only buttons expose an accessible name matching their title', () => {
    // Titles stay verbatim (pinned by admin.test.jsx via getByTitle); the
    // aria-label gives icon-only buttons a name independent of tooltip support.
    for (const name of [
      'Approve the pending account',
      'Suspend the account',
      'Reinstate the account',
      'Delete the user and their files',
      'Copy the code',
    ]) {
      expect(source).toContain(`aria-label="${name}"`);
      expect(source).toContain(`title="${name}"`);
    }
  });

  it('table column headers declare scope="col"', () => {
    const appScopes = combinedAppSource.match(/scope="col"/g) || [];
    const adminScopes = source.match(/scope="col"/g) || [];
    // Runs (6) + Compare column template (2 sites) = 8 in App.jsx (the
    // pre-R5 confusion header alone is 1, so this fails without the fix).
    expect(appScopes.length).toBeGreaterThanOrEqual(8);
    // Users (6) + Queue (6) + Invites (4) = 16 in AdminScreen.jsx (0 pre-R5).
    expect(adminScopes.length).toBeGreaterThanOrEqual(16);
    // Self-check: the unscoped header form has none.
    expect(('<th className="th">Compare</th>'.match(/scope="col"/g) || []).length).toBe(0);
  });
});

describe('static guard: R6 split coverage (F1)', () => {
  // The combined scan must actually read the new files. If views/** or
  // components/** were unscanned, combinedAppSource would collapse to
  // App.jsx alone and every moved-string guard above would go blind; the
  // markers below live only in the moved files, so an App-only scan fails
  // here by construction.
  it('the combined scan covers App.jsx plus the views and components trees', () => {
    expect(scannedAppFiles.length).toBeGreaterThanOrEqual(10);
    expect(scannedAppFiles.some((file) => file.endsWith(join('views', 'AuthView.jsx')))).toBe(true);
    expect(scannedAppFiles.some((file) => file.endsWith(join('components', 'shared.jsx')))).toBe(true);
    expect(scannedAppFiles.some((file) => file.endsWith(join('components', 'metrics.jsx')))).toBe(true);
  });

  it('moved markers are present in the combined scan and absent from App.jsx alone', () => {
    for (const marker of ['disclosure-summary', 'runs-table-wrap', 'compare-metric', 'scope="col"']) {
      expect(combinedAppSource).toContain(marker);
      expect(appSource).not.toContain(marker);
    }
    // Guard self-check: an App-only scan really does lose these strings.
    expect('App.jsx without the moved strings'.includes('disclosure-summary')).toBe(false);
  });

  it('App.jsx shrank to the shell and defines no view or shared component', () => {
    const lines = appSource.split('\n').length;
    expect(lines).toBeLessThan(700);
    for (const name of [
      'AuthView', 'ModelsCatalog', 'RunsDashboard', 'RunDetails', 'CompareRuns',
      'PredictPanel', 'NewJob', 'ResultLine', 'EvaluationPanel', 'AuthProvider',
      'AuthContext', 'StatusMark', 'Breadcrumb',
    ]) {
      expect(appSource).not.toContain(`const ${name} =`);
    }
    // The shell itself stays: hash routing, ErrorBoundary key, default export.
    expect(appSource).toContain('class ErrorBoundary extends');
    expect(appSource).toContain('export default function App');
    expect(appSource).toContain('MainApp');
  });

  it('every moved definition appears exactly once across the scanned files', () => {
    const moved = [
      'AuthView', 'ModelsCatalog', 'RunsDashboard', 'RunDetails', 'CompareRuns',
      'PredictPanel', 'NewJob', 'ResultLine', 'EvaluationPanel', 'Bar',
      'ConfusionMatrix', 'PreprocessingReport', 'PredictionResult', 'RunEvents',
      'AuthProvider', 'groupModels', 'resultOf', 'headlineOf', 'formatMetric',
    ];
    for (const name of moved) {
      const defs = combinedAppSource.match(new RegExp(`\\bconst ${name} =`, 'g')) || [];
      expect(defs.length, name).toBe(1);
    }
    const contextDefs = combinedAppSource.match(/\bconst AuthContext =/g) || [];
    expect(contextDefs.length).toBe(1);
  });
});
