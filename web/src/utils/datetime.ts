/**
 * Timezone-aware datetime helpers.
 *
 * Background
 * ----------
 * The backend stores every ``DateTime`` column as a **naive UTC** value
 * (the SQLAlchemy ``DateTime`` type has no tz, but every crawler
 * normalises to UTC in :class:`RawArticle` before insert). When those
 * values flow through ``datetime.isoformat()`` they come out without
 * a timezone suffix, which ``dayjs`` then interprets as **local time**
 * — so for an Asia/Shanghai user a 10:00 (UTC) publish time renders as
 * 10:00 local, which is actually 18:00 UTC. The user sees the news
 * "8 hours earlier than expected".
 *
 * Fix
 * ---
 * 1. The backend (``app/api/v1/news.py::_iso_utc``) now emits an
 *    explicit ``+00:00`` suffix on every datetime field.
 * 2. These helpers parse incoming strings as UTC and convert to the
 *    Asia/Shanghai zone before formatting. Any value that already
 *    carries a timezone offset is honoured, so callers can pass epoch
 *    milliseconds, naive ISO strings, or ``Z``-suffixed strings — all
 *    end up rendered in Shanghai time.
 *
 * The runtime cost is one ``dayjs.extend(utc)`` / ``dayjs.extend(timezone)``
 * call (done lazily on first use) and an extra ``tz('Asia/Shanghai')``
 * hop per format — both negligible for the dozens of timestamps the UI
 * renders per page.
 */
import dayjs, { type Dayjs } from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';

let pluginsRegistered = false;
function ensurePlugins() {
  if (pluginsRegistered) return;
  dayjs.extend(utc);
  dayjs.extend(timezone);
  pluginsRegistered = true;
}

/** Display timezone for the platform. The team is China-based. */
export const DISPLAY_TZ = 'Asia/Shanghai';

/**
 * Parse a backend datetime value as UTC and return a ``Dayjs`` anchored
 * in :data:`DISPLAY_TZ`. Accepts:
 *
 * - ISO-8601 strings with or without a timezone suffix
 *   (``"2026-07-04T10:00:00+00:00"`` or the naive form
 *   ``"2026-07-04T10:00:00"`` — both are read as UTC)
 * - Epoch milliseconds (numbers or numeric strings)
 * - ``null`` / ``undefined`` / empty string — returns an invalid Dayjs
 *   so callers can short-circuit via :meth:`Dayjs.isValid`.
 */
export function toLocal(value: string | number | null | undefined): Dayjs {
  ensurePlugins();
  if (value === null || value === undefined || value === '') {
    // dayjs(undefined) / dayjs('') already produce an invalid Dayjs, so
    // we just route through the public API and let the caller branch on
    // isValid() — no need for a separate ``dayjs.invalid`` helper.
    return dayjs(value) as unknown as Dayjs;
  }
  // Epoch ms — the SSE market stream emits these.
  if (typeof value === 'number' || /^\d+$/.test(String(value))) {
    return dayjs.utc(Number(value)).tz(DISPLAY_TZ);
  }
  const raw = String(value);
  // Force UTC for naive strings (no ``Z`` / ``+HH:MM`` / ``-HH:MM``).
  const looksAware = /[zZ]|[+-]\d{2}:?\d{2}$/.test(raw);
  const utcString = looksAware ? raw : `${raw}Z`;
  return dayjs.utc(utcString).tz(DISPLAY_TZ);
}

/**
 * Format an absolute datetime in the local display timezone.
 *
 * @param value  Backend datetime (naive UTC ISO, TZ-aware ISO, or epoch ms).
 * @param fmt    dayjs format string (defaults to ``YYYY-MM-DD HH:mm``).
 * @param empty  Fallback when the input is missing/invalid.
 */
export function formatDateTime(
  value: string | number | null | undefined,
  fmt = 'YYYY-MM-DD HH:mm',
  empty = '-',
): string {
  const t = toLocal(value);
  return t.isValid() ? t.format(fmt) : empty;
}

/** ``2026-07-04 10:00:00`` — verbose tooltip timestamp. */
export function formatDateTimeSeconds(
  value: string | number | null | undefined,
  empty = '',
): string {
  return formatDateTime(value, 'YYYY-MM-DD HH:mm:ss', empty);
}

/** ``07-04 10:00`` — compact card / row timestamp. */
export function formatDateTimeCompact(
  value: string | number | null | undefined,
  empty = '',
): string {
  return formatDateTime(value, 'MM-DD HH:mm', empty);
}

/**
 * Approximate "x 分钟前 / x 小时前 / x 天前 / 绝对日期" formatter.
 *
 * The diff is computed against the user's wall clock in :data:`DISPLAY_TZ`
 * (so a "1 minute ago" article published 30 s ago really is 30 s ago
 * in Shanghai, not 30 s + tz offset in UTC).
 */
export function formatRelative(
  value: string | number | null | undefined,
  options: { withTimeAfterDays?: number } = {},
): string {
  const t = toLocal(value);
  if (!t.isValid()) return '';
  // Diff in minutes, computed in the same tz so DST / tz shifts line up.
  const now = dayjs().tz(DISPLAY_TZ);
  const diff = now.diff(t, 'minute');
  // Future timestamps (e.g. cninfo announcements whose published_at is
  // disclosure-day midnight) must not render as "刚刚".
  if (diff < 0) {
    return t.isSame(now, 'day') ? `今天 ${t.format('HH:mm')}` : t.format('YYYY-MM-DD HH:mm');
  }
  if (diff < 1) return '刚刚';
  if (diff < 60) return `${diff} 分钟前`;
  const h = Math.floor(diff / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.floor(h / 24);
  const cutoff = options.withTimeAfterDays ?? 30;
  if (d < cutoff) return `${d} 天前`;
  return t.format('YYYY-MM-DD');
}

/**
 * Build an ISO string suitable for sending to the backend as a query
 * param. The backend's ``_parse_iso`` helper treats naive strings as
 * UTC, so we explicitly include the ``Z`` suffix when the caller has
 * not set a tz on the Dayjs object.
 */
export function toUtcIso(d: Dayjs | null | undefined): string | undefined {
  if (!d) return undefined;
  // ``Dayjs`` is a function object; ``typeof d.tz === 'function'``
  // tells us the tz plugin was extended onto this instance.
  if (typeof (d as unknown as { tz?: unknown }).tz === 'function') {
    return (d as unknown as { tz: (tz: string) => { utc: () => { toISOString: () => string } } })
      .tz(DISPLAY_TZ)
      .utc()
      .toISOString();
  }
  return d.toISOString();
}