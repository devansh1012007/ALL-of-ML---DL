import { describe, it, expect } from 'vitest';
import { formatBytes, timeAgo, formatWhen } from '../format.js';

// Canonical formatter contract (plan §R1 + §6 F2):
//   formatBytes(null/undefined) -> "—"   unknown, never a zero
//   formatBytes(0)              -> "0 B" true zero, distinct from unknown
//   < 1024 B / KB / MB / GB progression in B, KB, MB, GB
//   timeAgo/formatWhen(null)    -> "—"

const isoAt = (offsetMs) => new Date(Date.now() + offsetMs).toISOString();
const MIN = 60 * 1000;

describe('formatBytes', () => {
  it('unknown (null/undefined) renders as "—", not zero', () => {
    expect(formatBytes(null)).toBe('—');
    expect(formatBytes(undefined)).toBe('—');
  });

  it('true zero is "0 B", distinct from unknown', () => {
    expect(formatBytes(0)).toBe('0 B');
  });

  it('formats bytes under one kibibyte as integer B', () => {
    expect(formatBytes(1)).toBe('1 B');
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(1023)).toBe('1023 B');
  });

  it('carries over at 1024 to KB', () => {
    expect(formatBytes(1024)).toBe('1.0 KB');
    expect(formatBytes(1536)).toBe('1.5 KB');
  });

  it('carries over at one mebibyte to MB', () => {
    expect(formatBytes(1024 * 1024)).toBe('1.0 MB');
    expect(formatBytes(2.5 * 1024 * 1024)).toBe('2.5 MB');
  });

  it('formats large values in GB', () => {
    expect(formatBytes(1024 * 1024 * 1024)).toBe('1.00 GB');
    expect(formatBytes(5 * 1024 * 1024 * 1024)).toBe('5.00 GB');
  });
});

describe('timeAgo', () => {
  it('unknown (null/undefined/empty) renders as "—"', () => {
    expect(timeAgo(null)).toBe('—');
    expect(timeAgo(undefined)).toBe('—');
    expect(timeAgo('')).toBe('—');
  });

  it('a recent timestamp is "just now"', () => {
    expect(timeAgo(isoAt(-30 * 1000))).toBe('just now');
  });

  it('rounds minutes, hours and days', () => {
    expect(timeAgo(isoAt(-5 * MIN))).toBe('5 min ago');
    expect(timeAgo(isoAt(-3 * 60 * MIN))).toBe('3 h ago');
    expect(timeAgo(isoAt(-5 * 24 * 60 * MIN))).toBe('5 d ago');
  });

  it('an old timestamp falls back to the locale date', () => {
    const iso = isoAt(-40 * 24 * 60 * MIN);
    expect(timeAgo(iso)).toBe(new Date(iso).toLocaleDateString());
  });

  it('a future timestamp is clamped to "just now"', () => {
    expect(timeAgo(isoAt(10 * MIN))).toBe('just now');
  });
});

describe('formatWhen', () => {
  it('unknown (null/undefined/empty) renders as "—"', () => {
    expect(formatWhen(null)).toBe('—');
    expect(formatWhen(undefined)).toBe('—');
    expect(formatWhen('')).toBe('—');
  });

  it('a valid timestamp renders the short locale date+time', () => {
    const iso = '2026-11-08T10:30:00Z';
    expect(formatWhen(iso)).toBe(
      new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
    );
  });
});
