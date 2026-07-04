import { useEffect, useState } from 'react';

/**
 * Phase 1 (2026-07-05): theme 命名从 'clean' | 'dark' 改为 'light' | 'dark'.
 *
 * 历史:
 *   - 早期: 'terminal' | 'print' (两套实验性主题)
 *   - v1:    'clean' | 'dark'
 *   - 现在: 'light' | 'dark' (print 已退役, 用户 localStorage 里残留值自动迁到 'light')
 *
 * 本地存储 key 保持 `ad-research-theme` 不变 — 老用户平滑迁移。
 */
export type Theme = 'light' | 'dark';

/** Legacy value aliases accepted on read.  Never returned. */
const LEGACY_ALIAS: Record<string, Theme> = {
  terminal: 'dark',
  print: 'light',
  clean: 'light',
  light: 'light',
  dark: 'dark',
};

const STORAGE_KEY = 'ad-research-theme';

function migrateLegacyTheme(stored: string | null): Theme {
  if (stored && stored in LEGACY_ALIAS) return LEGACY_ALIAS[stored];
  return 'light';
}

export function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'light';
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return migrateLegacyTheme(stored);
  } catch {
    // ignore
  }
  return 'light';
}

/**
 * Read/write the persisted theme.  Side effect: keeps the
 * `<html data-theme="...">` attribute in sync and dispatches a
 * `themechange` custom event so ConfigProvider can re-render.
 *
 * Print theme is retired — calling `setTheme('print')` is a no-op
 * (treated as `setTheme('light')`).
 */
export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute('data-theme', theme);
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // ignore
    }
    // Notify ConfigProvider listeners (in main.tsx)
    document.dispatchEvent(new CustomEvent('themechange', { detail: theme }));
  }, [theme]);

  return [theme, setThemeState];
}