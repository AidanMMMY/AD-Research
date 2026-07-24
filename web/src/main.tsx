import React, { useEffect, useMemo, useState } from 'react';
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
import { readCssVarStrict } from '@/utils/cssVar';
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

  // 2026-07-24: 改用 readCssVarStrict + useMemo。
  // 旧实现给每个 token 配 dark 字面值 fallback —— 但 light base 在 :root
  // 已声明所有 token，浏览器里 getComputedStyle 永远拿到非空，fallback
  // 是误导性死代码（且 dark-first 字面值让新人以为 light 主题没生效）。
  // Strict 模式在 token 缺失时 console.warn，把 silent failure 显形。
  // useMemo 防止 themechange 触发整个 AntD 子树 re-render。
  const css = (name: string) => readCssVarStrict(name);
  const isDark = mode === 'dark';

  return useMemo(() => ({
    algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: css('--accent'),
      colorPrimaryHover: css('--accent-hover'),
      colorPrimaryActive: css('--accent-active'),
      colorInfo: css('--color-info'),
      colorSuccess: css('--color-success'),
      colorWarning: css('--color-warning'),
      colorError: css('--color-error'),
      colorBgBase: css('--bg-base'),
      colorBgContainer: css('--card-bg'),
      colorBgElevated: css('--bg-elevated'),
      colorTextBase: css('--text-primary'),
      colorTextSecondary: css('--text-secondary'),
      colorTextTertiary: css('--text-tertiary'),
      colorTextLightSolid: css('--text-on-accent'),
      colorBorder: css('--border-default'),
      colorBorderSecondary: css('--bg-elevated'),
      borderRadius: parseInt(css('--radius-md') || '8', 10),
      borderRadiusSM: parseInt(css('--radius-sm') || '4', 10),
      borderRadiusLG: parseInt(css('--radius-xl') || '12', 10),
      borderRadiusXS: 2,
      fontFamily:
        css('--font-sans') ||
        'Inter, "SF Pro Display", -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif',
      fontFamilyCode:
        css('--font-mono') ||
        '"JetBrains Mono", "SF Mono", "Fira Code", "Cascadia Code", monospace',
      controlHeight: 36,
      controlHeightSM: 30,
      controlHeightLG: 44,
    },
    components: {
      Table: {
        headerBg: 'transparent',
        headerColor: css('--text-tertiary'),
        headerSplitColor: 'transparent',
        rowHoverBg: css('--bg-hover'),
        borderColor: css('--border-default'),
        cellPaddingInline: 16,
        cellPaddingBlock: 14,
        headerBorderRadius: 0,
      },
      Button: {
        borderRadius: parseInt(css('--radius-md') || '8', 10),
        borderRadiusSM: parseInt(css('--radius-sm') || '4', 10),
        primaryShadow: 'none',
      },
      Card: {
        borderRadius: parseInt(css('--card-radius') || '12', 10),
        borderRadiusLG: parseInt(css('--radius-2xl') || '16', 10),
        colorBgContainer: css('--card-bg'),
      },
      Modal: {
        borderRadiusLG: parseInt(css('--radius-xl') || '12', 10),
        colorBgElevated: css('--bg-elevated'),
      },
      Drawer: {
        colorBgElevated: css('--bg-elevated'),
      },
      Tag: {
        borderRadiusSM: parseInt(css('--radius-sm') || '4', 10),
        defaultBg: css('--bg-surface'),
        defaultColor: css('--text-secondary'),
      },
      Input: {
        borderRadius: parseInt(css('--radius-md') || '8', 10),
        colorBgContainer: css('--bg-input'),
        activeBorderColor: css('--accent'),
        activeShadow: `0 0 0 2px ${css('--accent-glow')}`,
      },
      Select: {
        borderRadius: parseInt(css('--radius-md') || '8', 10),
        colorBgContainer: css('--bg-input'),
        optionSelectedBg: css('--accent-dim'),
        optionSelectedColor: css('--accent'),
      },
      Tabs: {
        inkBarColor: css('--accent'),
        itemSelectedColor: css('--text-primary'),
        itemHoverColor: css('--text-secondary'),
        itemColor: css('--text-tertiary'),
      },
      Alert: {
        colorError: css('--color-error'),
        colorErrorBg: css('--color-error-dim'),
        colorErrorBorder: css('--color-error-border'),
        colorWarning: css('--color-warning'),
        colorWarningBg: css('--color-warning-dim'),
        colorWarningBorder: css('--color-warning-border'),
        colorSuccess: css('--color-success'),
        colorSuccessBg: css('--color-success-dim'),
        colorSuccessBorder: css('--color-success-border'),
        colorInfo: css('--color-info'),
        colorInfoBg: css('--accent-dim'),
        colorInfoBorder: css('--accent-border'),
      },
    },
  }), [isDark]);
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
