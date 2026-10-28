// Colours are CSS variables (space-separated RGB, see styles.css) so that a
// utility such as bg-accent/15 keeps working and one place defines the palette.
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ['./index.html', './App.jsx', './AdminScreen.jsx', './main.jsx'],
  theme: {
    extend: {
      colors: {
        canvas: token('canvas'),
        surface: token('surface'),
        raised: token('raised'),
        rule: token('rule'),
        strong: token('strong'),
        ink: token('ink'),
        muted: token('muted'),
        faint: token('faint'),
        accent: token('accent'),
        'accent-hover': token('accent-hover'),
        'accent-ink': token('accent-ink'),
        ok: token('ok'),
        warn: token('warn'),
        bad: token('bad'),
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'ui-sans-serif', 'system-ui', '-apple-system', '"Segoe UI"', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      maxWidth: { page: '68rem', prose: '42rem' },
    },
  },
  plugins: [],
};
