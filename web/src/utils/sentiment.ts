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
