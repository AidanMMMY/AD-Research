/**
 * Unit tests for `formatRelative` (src/utils/datetime.ts).
 *
 * Focus: future timestamps (e.g. cninfo announcements whose
 * ``published_at`` is disclosure-day midnight) must render as an
 * absolute date/time, never as "刚刚".
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { formatRelative } from '@/utils/datetime';

describe('formatRelative', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Fix "now" at 2026-07-20 10:00 Asia/Shanghai.
    vi.setSystemTime(new Date('2026-07-20T02:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders recent past timestamps as relative text', () => {
    expect(formatRelative('2026-07-20T01:59:40Z')).toBe('刚刚');
    expect(formatRelative('2026-07-20T09:55:00+08:00')).toBe('5 分钟前');
    expect(formatRelative('2026-07-20T07:00:00+08:00')).toBe('3 小时前');
  });

  it('renders future timestamps on the same day as 今天 HH:mm', () => {
    expect(formatRelative('2026-07-20T14:00:00+08:00')).toBe('今天 14:00');
  });

  it('renders future timestamps on other days as absolute datetime', () => {
    expect(formatRelative('2026-07-22T09:30:00+08:00')).toBe('2026-07-22 09:30');
  });

  it('falls back to absolute date beyond the cutoff', () => {
    expect(formatRelative('2026-06-01T10:00:00+08:00')).toBe('2026-06-01');
  });
});
