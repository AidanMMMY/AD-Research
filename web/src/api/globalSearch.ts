import { menuRoutes, sidebarGroups, type SidebarGroupKey } from '@/routes';

/**
 * Global search / command-palette suggestion API.
 *
 * Command Palette (⌘K, 2026-07-16) — this module is the single source of
 * suggestions rendered by <CommandPalette>. It merges three kinds of results:
 *
 *   • 'page'       — client-side page registry, derived from `menuRoutes` +
 *                    `sidebarGroups` in routes.tsx (no network round-trip, so
 *                    type-ahead stays instant).
 *   • 'instrument' — MOCK for now; wired to the backend fuzzy-search endpoint
 *                    in a later pass (placeholder returns []).
 *   • 'news'       — MOCK for now; same as above.
 *
 * The palette debounces its input by 250ms before calling `globalSearch`.
 */

export type SuggestionType = 'page' | 'instrument' | 'news';

export interface Suggestion {
  type: SuggestionType;
  /** Stable identity within a type (page path / instrument code / news id). */
  id: string;
  title: string;
  subtitle?: string;
  /** react-router target the palette navigates to on select. */
  href: string;
}

export interface GlobalSearchResult {
  data: Suggestion[];
}

/** A single navigable page in the app, distilled from the route menu config. */
export interface PageEntry {
  id: string;
  name: string;
  path: string;
  group?: SidebarGroupKey;
  groupLabel?: string;
  icon?: string;
}

// group key → human label, so page subtitles read "行情与市场 · /correlation".
const GROUP_LABELS: Record<string, string> = Object.fromEntries(
  sidebarGroups.map((g) => [g.key, g.label])
);

/**
 * Hardcoded page registry built from routes.tsx `menuRoutes`.
 * Every route that surfaces in the sidebar menu is searchable.
 */
export const pageRegistry: PageEntry[] = menuRoutes
  .filter((r) => r.menu)
  .map((r) => ({
    id: r.path,
    name: r.menu!.label || r.menu!.name,
    path: r.path,
    group: r.menu!.group,
    groupLabel: r.menu!.group ? GROUP_LABELS[r.menu!.group] : undefined,
    icon: r.menu!.icon,
  }));

/**
 * Type-ahead filter over the page registry. Matches on both display name and
 * path so "corr" and "/correlation" both hit 相关性分析. Empty query returns
 * the full registry (so ⌘K with no typing shows every page).
 */
export function filterPages(query: string): PageEntry[] {
  const q = query.trim().toLowerCase();
  if (!q) return pageRegistry;
  return pageRegistry.filter(
    (p) => p.name.toLowerCase().includes(q) || p.path.toLowerCase().includes(q)
  );
}

function pageToSuggestion(p: PageEntry): Suggestion {
  return {
    type: 'page',
    id: p.id,
    title: p.name,
    subtitle: p.groupLabel ? `${p.groupLabel} · ${p.path}` : p.path,
    href: p.path,
  };
}

// ── MOCK backends — return [] until the search API lands. Kept as async
//    functions so the call sites don't change when we swap in `client.get`.
async function searchInstruments(_query: string): Promise<Suggestion[]> {
  // TODO(backend): GET /search/instruments?q=... → { code, name } → Suggestion
  return [];
}

async function searchNews(_query: string): Promise<Suggestion[]> {
  // TODO(backend): GET /search/news?q=... → { id, title, source } → Suggestion
  return [];
}

/**
 * Aggregate suggestions across pages + instruments + news.
 *
 * Ordering contract (relied on by the palette's section rendering):
 * pages first, then instruments, then news.
 */
export async function globalSearch(query: string): Promise<GlobalSearchResult> {
  const q = query.trim();

  const pages = filterPages(q).map(pageToSuggestion);

  const [instruments, news] = await Promise.all([
    searchInstruments(q),
    searchNews(q),
  ]);

  return { data: [...pages, ...instruments, ...news] };
}

export default globalSearch;
