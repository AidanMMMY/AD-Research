import { useEffect, useState } from 'react';

export type Theme = 'clean' | 'dark';

const STORAGE_KEY = 'ad-research-theme';

function migrateLegacyTheme(stored: string | null): Theme {
  if (stored === 'terminal') return 'dark';
  if (stored === 'print') return 'clean';
  if (stored === 'dark' || stored === 'clean') return stored;
  return 'clean';
}

export function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'clean';
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return migrateLegacyTheme(stored);
  } catch {
    // ignore
  }
  return 'clean';
}

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
