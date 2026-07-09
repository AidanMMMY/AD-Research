/** Macro indicator frontend types.
 *
 * Mirrors `app/schemas/macro.py` (Phase 2 additions). Backend is the
 * source of truth — keep this file in sync manually.
 */

export type MacroRegion = 'cn' | 'eu' | 'us' | 'global';

export interface MacroObservation {
  id: number;
  code: string;
  region: MacroRegion;
  name_zh: string;
  name_en: string | null;
  unit: string | null;
  /** ISO date (YYYY-MM-DD). */
  period: string;
  value: number;
  source: string;
  fetched_at: string | null;
}

export interface MacroIndicatorListResponse {
  items: MacroObservation[];
  total: number;
  page: number;
  page_size: number;
}

export interface MacroCodeInfo {
  code: string;
  region: MacroRegion;
  name_zh: string;
  name_en: string | null;
  unit: string | null;
  source: string;
  latest_period: string | null;
  latest_value: number | null;
}

export interface MacroCodeListResponse {
  items: MacroCodeInfo[];
}

export interface MacroLatestItem {
  code: string;
  region: MacroRegion;
  name_zh: string;
  name_en: string | null;
  unit: string | null;
  source: string;
  /** ISO date (YYYY-MM-DD). */
  period: string;
  value: number;
  prev_value: number | null;
  change_pct: number | null;
  fetched_at: string | null;
  /**
   * Localized "why is this stale" hint surfaced by the backend when the
   * row's period lags today by more than the data source's expected
   * cadence (e.g. FRED H.10 weekly FX lag). Frontend reads this to render
   * the small warning badge on Dashboard / Macro tiles.
   */
  freshness_hint?: string | null;
}

export interface MacroLatestResponse {
  items: MacroLatestItem[];
  region: MacroRegion | null;
}

export interface MacroRefreshResult {
  fetched: number;
  written: number;
  per_series: Record<string, { fetched: number; written: number }>;
  failed: string[];
}

export interface MacroListParams {
  region?: MacroRegion;
  code?: string;
  start_period?: string;
  end_period?: string;
  page?: number;
  page_size?: number;
}
