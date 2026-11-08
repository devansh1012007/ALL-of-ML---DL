// Canonical formatters shared by App.jsx and AdminScreen.jsx.
//
// Consolidates the two divergent copies (App: formatBytes rounded KB with no
// null guard and timeAgo "" for unknown; Admin: null-safe "—" semantics).
// Canonical semantics (plan §R1 + §6 F2):
//
//   formatBytes(null/undefined) -> "—"    unknown is never shown as a zero
//   formatBytes(0)              -> "0 B"  a true zero stays a zero
//   formatBytes                 -> B / KB / MB / GB progression (1024-based)
//   timeAgo(null/undefined/"")  -> "—"
//   formatWhen(null/undefined/"")-> "—"
//
// P2a unknown handling depends on this true-zero vs unknown split, so the
// null -> "—" guard must never be flattened into a numeric zero.

export const formatBytes = (bytes) => {
  if (bytes === null || bytes === undefined) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
};

// "3 min ago", with the exact time left to a tooltip.
export const timeAgo = (iso) => {
  if (!iso) return '—';
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 45) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} d ago`;
  return new Date(iso).toLocaleDateString();
};

export const formatWhen = (iso) => {
  if (!iso) return '—';
  const date = new Date(iso);
  return date.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
};
