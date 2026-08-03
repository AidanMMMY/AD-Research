/**
 * Sentiment color & label dictionaries (shared across dashboard / news / detail pages).
 *
 * Why centralized: 6+ pages used to inline identical `SENTIMENT_COLORS` /
 * `SENTIMENT_LABELS` records, drifting over time. Central version uses the
 * `cssVar()` token map (CSS variables) so dark / light themes stay in sync.
 */

export type SentimentLabel =
  | 'positive'
  | 'neutral'
  | 'negative'
  | 'bullish'
  | 'bearish';

export const SENTIMENT_COLORS: Record<string, string> = {
  positive: 'var(--color-rise)',
  bullish: 'var(--color-rise)',
  neutral: 'var(--text-secondary)',
  negative: 'var(--color-fall)',
  bearish: 'var(--color-fall)',
};

export const SENTIMENT_LABELS: Record<string, string> = {
  positive: '看多',
  bullish: '看多',
  neutral: '中性',
  negative: '看空',
  bearish: '看空',
};

export function getSentimentColor(label: string): string {
  return SENTIMENT_COLORS[label as SentimentLabel] ?? 'var(--text-secondary)';
}

export function getSentimentLabel(label: string): string {
  return SENTIMENT_LABELS[label as SentimentLabel] ?? label;
}

/**
 * Normalize ``sentiment_score`` regardless of backend convention
 * (N2+I3 统一双标度, 2026-08-03).
 *
 * Backend stores either the ``-100..+100`` integer range (legacy pipeline)
 * or the ``-1..+1`` float range (newer pipeline). Detect by magnitude and
 * return the uniform ``-1..+1`` float so every surface (card tooltip,
 * drawer tooltip, detail badge, instrument sentiment bar) renders the
 * same number for the same row.
 */
export function normalizeSentimentScore(score: number): number {
  if (!Number.isFinite(score)) return 0;
  // |x| > 2 cannot be a -1..+1 float → treat as -100..+100 scale.
  return Math.abs(score) > 2 ? score / 100 : score;
}

/**
 * Display helper: uniform "-0.78" style string, em-dash for missing /
 * non-finite input. Accepts null/undefined so callers don't need their
 * own null guard before rendering.
 */
export function formatSentimentScore(
  score: number | null | undefined,
): string {
  if (score == null || !Number.isFinite(score)) return '—';
  return normalizeSentimentScore(score).toFixed(2);
}
