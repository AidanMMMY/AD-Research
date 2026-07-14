/**
 * Map a macro indicator code to its display region.
 *
 * Single source of truth shared by Dashboard (Market Pulse tiles),
 * Macro page, GlobalMarkets, etc. — avoids the "click tile, jump to
 * Macro, can't find the code" fragmentation when the mapping drifts.
 *
 * Region values match the Macro page's `region` state: 'us' | 'eu' | 'cn' | 'global'.
 */
export type MacroRegion = 'us' | 'eu' | 'cn' | 'global';

export function codeToRegion(code: string | null | undefined): MacroRegion {
  if (!code) return 'us';
  const c = code.toLowerCase();
  if (c.startsWith('us_') || c.startsWith('usd_') || c.startsWith('us_t10y')) return 'us';
  if (c.startsWith('eu_')) return 'eu';
  if (c.startsWith('global_')) return 'global';
  // China macro: gdp_yoy / cpi_yoy / ppi_yoy / m2_yoy / pmi_* / shibor_*
  return 'cn';
}