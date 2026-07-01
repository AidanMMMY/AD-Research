import { useEffect, useState } from 'react';

export type Theme = 'terminal' | 'print';

const STORAGE_KEY = 'ad-research-theme';

export function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'terminal';
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === 'print' || stored === 'terminal') return stored;
  } catch {
    // ignore
  }
  return 'terminal';
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'print') {
      root.setAttribute('data-theme', 'print');
    } else {
      root.removeAttribute('data-theme');
    }
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
