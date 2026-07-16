import { useEffect, useState } from 'react';

/**
 * Theme — P3 feature (2026-07-16): adds `'system'` option to track OS-level
 * `prefers-color-scheme` automatically.  New users default to `'system'` so
 * the app follows their OS without configuration; existing users keep
 * whatever they had stored (`'light'` / `'dark'`) and can opt into
 * `'system'` from the header toggle.
 *
 * Phase 1 (2026-07-05): theme 命名从 'clean' | 'dark' 改为 'light' | 'dark'.
 * 历史:
 *   - 早期: 'terminal' | 'print' (两套实验性主题)
 *   - v1:   'clean' | 'dark'
 *   - 现在: 'light' | 'dark' | 'system' (print 已退役, 用户 localStorage
 *           里残留值自动迁到 'light')
 *
 * 本地存储 key 保持 `ad-research-theme` 不变 — 老用户平滑迁移。
 */
export type Theme = 'light' | 'dark' | 'system';

/** The two values that actually end up on the `data-theme` attribute. */
export type ResolvedTheme = 'light' | 'dark';

/** Legacy value aliases accepted on read.  Never returned. */
const LEGACY_ALIAS: Record<string, Theme> = {
  terminal: 'dark',
  print: 'light',
  clean: 'light',
  light: 'light',
  dark: 'dark',
  system: 'system',
};

const STORAGE_KEY = 'ad-research-theme';
const SYSTEM_DARK_MQ = '(prefers-color-scheme: dark)';

function migrateLegacyTheme(stored: string | null): Theme {
  if (stored && stored in LEGACY_ALIAS) return LEGACY_ALIAS[stored];
  return 'system';
}

/**
 * Read the OS's `prefers-color-scheme` setting once.
 * SSR-safe (returns 'light' when window is unavailable).
 */
export function getSystemPreference(): ResolvedTheme {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light';
  return window.matchMedia(SYSTEM_DARK_MQ).matches ? 'dark' : 'light';
}

/**
 * Resolve a `Theme` (possibly `'system'`) to the concrete value that should
 * be applied to `<html data-theme="...">`.  Called from main.tsx during
 * initial render (before React mounts) and from useTheme to keep the
 * attribute in sync.
 */
export function resolveTheme(theme: Theme): ResolvedTheme {
  return theme === 'system' ? getSystemPreference() : theme;
}

export function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'system';
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return migrateLegacyTheme(stored);
  } catch {
    // ignore
  }
  return 'system';
}

export interface UseThemeReturn {
  /** The user's selection — may be `'system'`. */
  theme: Theme;
  setTheme: (t: Theme) => void;
  /** The value actually applied to `<html data-theme="...">`. */
  effectiveTheme: ResolvedTheme;
  /** Live OS preference, exposed for tooltip / debugging. */
  systemPreference: ResolvedTheme;
}

/**
 * Read/write the persisted theme.  Side effects:
 *  - keeps `<html data-theme="...">` in sync with the *resolved* theme
 *    (always `'light'` or `'dark'`, never `'system'`)
 *  - persists the *user's* selection (so picking `'dark'` survives even
 *    when the OS preference flips)
 *  - listens to `matchMedia('(prefers-color-scheme: dark)').change` and
 *    refreshes `effectiveTheme` when the user is on `'system'` mode
 *  - dispatches a `themechange` custom event with the *resolved* theme so
 *    ConfigProvider can re-render.  Re-dispatches on OS changes (when on
 *    `'system'`) so antd picks up the new algorithm in one tick.
 */
export function useTheme(): UseThemeReturn {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);
  const [systemPreference, setSystemPreference] = useState<ResolvedTheme>(
    getSystemPreference,
  );

  // Subscribe to OS-level color-scheme changes (only meaningful in browser).
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia(SYSTEM_DARK_MQ);
    const handler = (e: MediaQueryListEvent) => {
      setSystemPreference(e.matches ? 'dark' : 'light');
    };
    // `addEventListener` is the standard API; the older `addListener`
    // shim only exists on Safari < 14 which we no longer support.
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const effectiveTheme: ResolvedTheme =
    theme === 'system' ? systemPreference : theme;

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const root = document.documentElement;
    root.setAttribute('data-theme', effectiveTheme);
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // ignore quota / privacy-mode failures
    }
    // Notify ConfigProvider listeners (main.tsx → useAntdTheme).  Pass the
    // *resolved* theme so antd's `darkAlgorithm` / `defaultAlgorithm`
    // stays correct on every OS preference change.
    document.dispatchEvent(
      new CustomEvent('themechange', { detail: effectiveTheme }),
    );
  }, [theme, effectiveTheme]);

  return {
    theme,
    setTheme: setThemeState,
    effectiveTheme,
    systemPreference,
  };
}
