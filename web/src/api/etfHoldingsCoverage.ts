/**
 * ETF Holdings Coverage / Stats / Blacklist — frontend API client.
 *
 * Backs the new "ETF 持仓覆盖率" dashboard card. Three endpoints are
 * wrapped:
 *
 *   - ``GET /etf-holdings/coverage/latest`` — single-shot for the card.
 *   - ``GET /etf-holdings/stats``           — per-snapshot history (newest
 *                                              first), used for the trend
 *                                              sparkline.
 *   - ``GET /etf-holdings/unavailable``     — the curated blacklist (33
 *                                              currency / physical-gold
 *                                              ETFs).
 *
 * All endpoints are JWT-protected by the global axios client.
 */
import client from './client';

export interface CoverageAlert {
  threshold_days: number;
  min_coverage_pct: number;
  actual_coverage_pct: number;
  severity: string;
}

export interface SnapshotCoverage {
  snapshot_date: string;
  etf_count: number;
  row_count: number;
  source_count: number;
  sources: string[];
  days_ago: number;
  eligible_etf_count: number;
  coverage_pct: number;
  coverage_alerts: CoverageAlert[];
}

export interface StatsResponse {
  snapshots: SnapshotCoverage[];
  unavailable_count: number;
  generated_at: string;
}

export interface CoverageResponse {
  coverage: SnapshotCoverage | null;
}

export interface UnavailableItem {
  etf_code: string;
  category: string;
  reason: string;
  marked_at: string | null;
  marked_by: string | null;
}

export interface UnavailableResponse {
  items: UnavailableItem[];
  count: number;
  generated_at: string;
}

export const etfHoldingsCoverageApi = {
  /** Per-snapshot history (newest first). */
  getStats: () => client.get<StatsResponse>('/etf-holdings/stats').then((r) => r.data),

  /** Single-shot most recent snapshot for the dashboard card. */
  getLatestCoverage: () =>
    client.get<CoverageResponse>('/etf-holdings/coverage/latest').then((r) => r.data),

  /** Coverage for a specific reporting period. Returns 404 when missing. */
  getCoverageFor: (snapshotDate: string) =>
    client
      .get<CoverageResponse>(`/etf-holdings/coverage/${snapshotDate}`)
      .then((r) => r.data),

  /** Curated 33-ETF structural blacklist. */
  getUnavailable: () =>
    client.get<UnavailableResponse>('/etf-holdings/unavailable').then((r) => r.data),
};

export default etfHoldingsCoverageApi;
