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

// ---------------------------------------------------------------------------
// 全球速览指数详情页（/global/:code）契约 —— GET /macro/indicators/{code}/detail
// 字段与后端响应一一对应，不得随意增删。
// ---------------------------------------------------------------------------

/** 宏观代码的逻辑类目（决定详情页涨跌口径与图表形态）。 */
export type MacroCategory = 'rate' | 'fx' | 'commodity' | 'index' | 'vol';

/** 单根 OHLC bar（has_ohlc=true 时返回）。 */
export interface MacroOhlcBar {
  /** ISO date (YYYY-MM-DD)。 */
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

/** 最新快照：值 + 日涨跌（百分比与绝对值双口径）。 */
export interface MacroIndicatorLatest {
  /** ISO date (YYYY-MM-DD)。 */
  period: string;
  value: number;
  prev_value: number | null;
  /** 日涨跌（已乘 100 的百分比本身，直接配 ReturnTagPct）。 */
  change_pct: number | null;
  /** 日涨跌绝对值（rate 类目 ×100 即 bp）。 */
  change_abs: number | null;
}

export interface MacroIndicatorStats {
  first_period: string | null;
  last_period: string | null;
  count: number;
  high_52w: number | null;
  low_52w: number | null;
}

/** 详情接口完整响应。has_ohlc=true → ohlc 非空画蜡烛；否则 ohlc=null、points 画折线。 */
export interface MacroIndicatorDetail {
  code: string;
  region: string;
  name_zh: string;
  name_en: string;
  unit: string;
  source: string;
  category: MacroCategory;
  has_ohlc: boolean;
  latest: MacroIndicatorLatest | null;
  stats: MacroIndicatorStats;
  ohlc: MacroOhlcBar[] | null;
  points: Array<{ period: string; value: number }>;
}
