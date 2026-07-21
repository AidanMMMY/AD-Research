import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import {
  getInitialTheme,
  resolveTheme,
  type ResolvedTheme,
} from '@/hooks/useTheme';
import { readCssVar } from '@/utils/cssVar';
import { reportWebVitals } from '@/utils/webVitals';
// 自托管字体（Inter + JetBrains Mono），统一跨平台字体体验
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/700.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';
import './styles/theme.css';
import './styles/global.css';

// Apply persisted theme synchronously to avoid flash of wrong theme.
// P3 (2026-07-16): also resolve `'system'` against `prefers-color-scheme`
// so the very first paint already matches the OS — without this the user
// would see a light flash before the React useEffect catches up.
// Dark-first (2026-07-21): `getInitialTheme()` defaults to `'dark'` for
// users without a stored preference, so the first paint is dark.
const initialResolved: ResolvedTheme = resolveTheme(getInitialTheme());
document.documentElement.setAttribute('data-theme', initialResolved);
// Default color convention attribute is applied by AppLayout after mount
// (settings store value is the source of truth; SSR/no-store fallback is
// "china" via the :root CSS rules above).

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

/**
 * Build antd v5 theme tokens from the v2 design system defined in theme.css.
 * All seed colors are read from CSS custom properties so antd components stay
 * in sync with the data-theme / data-accent attributes on <html>.
 * The data-color-convention attribute is untouched because it only affects
 * market rise/fall colors, which are not used by antd's base palette.
 */
const useAntdTheme = () => {
  // `data-theme` is always the resolved value ('light' | 'dark') — it never
  // holds the literal `'system'` because useTheme resolves before writing.
  const [mode, setMode] = useState<ResolvedTheme>(() =>
    typeof document !== 'undefined'
      ? (document.documentElement.getAttribute('data-theme') as ResolvedTheme) || 'dark'
      : 'dark',
  );

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<ResolvedTheme>).detail;
      setMode(detail === 'dark' ? 'dark' : 'light');
    };
    document.addEventListener('themechange', handler);
    return () => document.removeEventListener('themechange', handler);
  }, []);

  const css = (name: string, fallback: string) => readCssVar(name, fallback);
  const isDark = mode === 'dark';

  return {
    algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      // Fallbacks mirror the dark-theme defaults in theme.css (dark-first
      // since 2026-07-21); in the browser `readCssVar` always returns the
      // computed value for the active theme, so these only matter for
      // SSR / no-DOM rendering.
      colorPrimary: css('--accent', '#60A5FA'),
      colorPrimaryHover: css('--accent-hover', '#93BBFD'),
      colorPrimaryActive: css('--accent-active', '#3B82F6'),
      colorInfo: css('--color-info', '#60A5FA'),
      colorSuccess: css('--color-success', '#34D399'),
      colorWarning: css('--color-warning', '#EAB308'),
      colorError: css('--color-error', '#F87171'),
      colorBgBase: css('--bg-base', '#0D1117'),
      colorBgContainer: css('--card-bg', '#1C2128'),
      colorBgElevated: css('--bg-elevated', '#161B22'),
      colorTextBase: css('--text-primary', '#E6EDF3'),
      colorTextSecondary: css('--text-secondary', '#A0A0A0'),
      colorTextTertiary: css('--text-tertiary', '#9CA3AF'),
      colorTextLightSolid: css('--text-on-accent', '#0D1117'),
      colorBorder: css('--border-default', '#30363D'),
      colorBorderSecondary: css('--bg-elevated', '#161B22'),
      borderRadius: parseInt(css('--radius-md', '8px'), 10),
      borderRadiusSM: parseInt(css('--radius-sm', '4px'), 10),
      borderRadiusLG: parseInt(css('--radius-xl', '12px'), 10),
      borderRadiusXS: 2,
      fontFamily: css(
        '--font-sans',
        'Inter, "SF Pro Display", -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif',
      ),
      fontFamilyCode: css(
        '--font-mono',
        '"JetBrains Mono", "SF Mono", "Fira Code", "Cascadia Code", monospace',
      ),
      controlHeight: 36,
      controlHeightSM: 30,
      controlHeightLG: 44,
    },
    components: {
      Table: {
        headerBg: 'transparent',
        headerColor: css('--text-tertiary', '#9CA3AF'),
        headerSplitColor: 'transparent',
        rowHoverBg: css('--bg-hover', 'rgba(255, 255, 255, 0.05)'),
        borderColor: css('--border-default', '#30363D'),
        cellPaddingInline: 16,
        cellPaddingBlock: 14,
        headerBorderRadius: 0,
      },
      Button: {
        borderRadius: parseInt(css('--radius-md', '8px'), 10),
        borderRadiusSM: parseInt(css('--radius-sm', '4px'), 10),
        primaryShadow: 'none',
      },
      Card: {
        borderRadius: parseInt(css('--card-radius', '12px'), 10),
        borderRadiusLG: parseInt(css('--radius-2xl', '16px'), 10),
        colorBgContainer: css('--card-bg', '#1C2128'),
      },
      Modal: {
        borderRadiusLG: parseInt(css('--radius-xl', '12px'), 10),
        colorBgElevated: css('--bg-elevated', '#161B22'),
      },
      Drawer: {
        colorBgElevated: css('--bg-elevated', '#161B22'),
      },
      Tag: {
        borderRadiusSM: parseInt(css('--radius-sm', '4px'), 10),
        defaultBg: css('--bg-surface', '#1C2128'),
        defaultColor: css('--text-secondary', '#A0A0A0'),
      },
      Input: {
        borderRadius: parseInt(css('--radius-md', '8px'), 10),
        colorBgContainer: css('--bg-input', 'rgba(255, 255, 255, 0.04)'),
        activeBorderColor: css('--accent', '#60A5FA'),
        activeShadow: `0 0 0 2px ${css('--accent-glow', 'rgba(96, 165, 250, 0.15)')}`,
      },
      Select: {
        borderRadius: parseInt(css('--radius-md', '8px'), 10),
        colorBgContainer: css('--bg-input', 'rgba(255, 255, 255, 0.04)'),
        optionSelectedBg: css('--accent-dim', 'rgba(96, 165, 250, 0.12)'),
        optionSelectedColor: css('--accent', '#60A5FA'),
      },
      Tabs: {
        inkBarColor: css('--accent', '#60A5FA'),
        itemSelectedColor: css('--text-primary', '#E6EDF3'),
        itemHoverColor: css('--text-secondary', '#A0A0A0'),
        itemColor: css('--text-tertiary', '#9CA3AF'),
      },
      Alert: {
        colorError: css('--color-error', '#F87171'),
        colorErrorBg: css('--color-error-dim', 'rgba(248, 113, 113, 0.14)'),
        colorErrorBorder: css('--color-error-border', 'rgba(248, 113, 113, 0.30)'),
        colorWarning: css('--color-warning', '#EAB308'),
        colorWarningBg: css('--color-warning-dim', 'rgba(234, 179, 8, 0.12)'),
        colorWarningBorder: css('--color-warning-border', 'rgba(234, 179, 8, 0.25)'),
        colorSuccess: css('--color-success', '#34D399'),
        colorSuccessBg: css('--color-success-dim', 'rgba(52, 211, 153, 0.14)'),
        colorSuccessBorder: css('--color-success-border', 'rgba(52, 211, 153, 0.30)'),
        colorInfo: css('--color-info', '#60A5FA'),
        colorInfoBg: css('--accent-dim', 'rgba(96, 165, 250, 0.12)'),
        colorInfoBorder: css('--accent-border', 'rgba(96, 165, 250, 0.25)'),
      },
    },
  };
};

function ThemedApp() {
  const antdTheme = useAntdTheme();
  return (
    <ConfigProvider locale={zhCN} theme={antdTheme}>
      <App />
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemedApp />
    </QueryClientProvider>
  </React.StrictMode>,
);

// P7c (2026-07-16): start Web Vitals observers once React has begun
// mounting. The reporter is idempotent — multiple calls are safe.
reportWebVitals();
