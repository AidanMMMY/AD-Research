/* ============================================================
   CSS Variable Utilities

   Low-level readers for CSS custom properties on :root.

   注意（2026-08-03 设计系统波 1）：图表取色解析器已收敛为单一事实源
   —— `chartColors.ts` 的 `resolveChartColor` / `resolveChartColors`
   （裸 token 名 API + 内置暗色 DEFAULT_FALLBACKS）。本文件只保留
   readCssVar / readCssVarStrict 两个底层读取器，新代码不要再在这里
   添加 resolve* 封装，避免出现第二套解析逻辑。
   ============================================================ */

/** Read a CSS custom property value from :root. */
export function readCssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/**
 * Strict CSS var reader — returns the computed value or '' when missing.
 * Use this when the caller MUST know whether the token is defined (e.g.
 * AntD theme configuration), so silent dark-fallback doesn't masquerade
 * as a valid value when the token is absent in the active theme.
 *
 * Emits a one-time console.warn per missing token so silent failure
 * becomes visible at dev time.
 */
const _warnedMissingTokens = new Set<string>();
export function readCssVarStrict(name: string): string {
  if (typeof window === 'undefined') return '';
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  if (!value && !_warnedMissingTokens.has(name)) {
    _warnedMissingTokens.add(name);
    // eslint-disable-next-line no-console
    console.warn(
      `[cssVar] Token ${name} is not defined on :root for the active theme. ` +
      'Check theme.css — both :root (light base) and :root[data-theme="dark"] ' +
      'must declare this token, otherwise consumers fall back to defaults.'
    );
  }
  return value;
}