/**
 * ETF Holdings History — frontend API client.
 *
 * Backs the new ``/etfs/:code/holdings-history`` AD-Research page that
 * lets users browse, compare, and diff the quarterly top-10 holdings
 * disclosed by ETF issuers.
 *
 * Three endpoints are wrapped:
 *
 *   - ``GET /etfs/{code}/holdings/snapshots`` — list of available
 *     reporting-period dates (newest first).
 *   - ``GET /etfs/{code}/holdings?date=YYYY-MM-DD`` — holdings for a
 *     single reporting period (latest when no ``date`` is supplied).
 *   - ``GET /etfs/{code}/holdings/diff?from=…&to=…`` — per-holding
 *     diff between two reporting periods, plus aggregate counters
 *     (added / removed / increased / decreased / unchanged).
 *
 * All endpoints are JWT-protected by the global axios client.
 */
import client from './client';
import type {
  ETFHoldingDiffResponse,
  ETFHoldingResponse,
  ETFHoldingSnapshotsResponse,
} from '@/types/instrument';

export interface EtfHoldingsHistoryParams {
  /** Reporting-period date (YYYY-MM-DD). Omit to fetch the latest snapshot. */
  date?: string;
  /** Source tag, reserved for future routing — currently ignored. */
  source?: string;
}

export interface EtfHoldingsDiffParams {
  /** Earlier reporting date. */
  from: string;
  /** Later reporting date. */
  to: string;
}

export const etfHoldingsHistoryApi = {
  /**
   * List every reporting-period snapshot available for an ETF.
   * Returned in reverse chronological order so callers can default
   * to the most recent period without re-sorting.
   */
  listSnapshots: (code: string) =>
    client
      .get<ETFHoldingSnapshotsResponse>(`/etfs/${code}/holdings/snapshots`)
      .then((r) => r.data),

  /**
   * Fetch the holdings for a specific reporting period. When
   * ``params.date`` is omitted, the backend returns the latest
   * snapshot (backwards-compatible with the original endpoint).
   */
  getHoldings: (code: string, params?: EtfHoldingsHistoryParams) =>
    client
      .get<ETFHoldingResponse>(`/etfs/${code}/holdings`, { params })
      .then((r) => r.data),

  /**
   * Compute per-holding deltas between two reporting periods and
   * return aggregate counters the UI uses as KPIs.
   */
  diffHoldings: (code: string, params: EtfHoldingsDiffParams) =>
    client
      .get<ETFHoldingDiffResponse>(`/etfs/${code}/holdings/diff`, { params })
      .then((r) => r.data),
};

export default etfHoldingsHistoryApi;
