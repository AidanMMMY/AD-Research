/**
 * Unit tests for the unified chart color resolver
 * (src/utils/chartColors.ts) — 2026-08-03 设计系统波 1 收敛后，
 * 这是全站图表取色的唯一入口（cssVar.ts 的第二套 resolveChartColor
 * 已删除）。
 *
 * Focus:
 *   - 裸 token 名 API：'--x' 走 getComputedStyle，未定义时回退到
 *     内置 DEFAULT_FALLBACKS（暗色默认）或显式 fallback；
 *   - 字面量（hex/rgb）原样透传；
 *   - token 路径：documentElement 上真正定义了变量时必须读到计算值。
 */
import { afterEach, describe, expect, it } from 'vitest';
import {
  resolveChartColor,
  resolveChartColors,
  subscribeChartThemeCache,
} from '@/utils/chartColors';

afterEach(() => {
  // 清理每个用例写到 :root 的内联自定义属性，避免用例间串扰。
  document.documentElement.removeAttribute('style');
});

describe('resolveChartColor', () => {
  it('passes literal colors through unchanged', () => {
    expect(resolveChartColor('#FF8585')).toBe('#FF8585');
    expect(resolveChartColor('rgba(96, 165, 250, 0.12)')).toBe(
      'rgba(96, 165, 250, 0.12)',
    );
  });

  it('falls back to the built-in dark default for known tokens', () => {
    // jsdom 的 :root 未加载 theme.css → --color-rise 未定义，
    // 应返回 DEFAULT_FALLBACKS 里的暗色值（dark-first 约定）。
    expect(resolveChartColor('--color-rise')).toBe('#FF8585');
    expect(resolveChartColor('--color-fall')).toBe('#7DCB99');
    expect(resolveChartColor('--color-neutral')).toBe('#888888');
  });

  it('prefers an explicit fallback over the built-in default', () => {
    expect(resolveChartColor('--color-rise', '#C0392B')).toBe('#C0392B');
  });

  it('returns #000000 for unknown tokens without a fallback', () => {
    expect(resolveChartColor('--does-not-exist')).toBe('#000000');
  });

  it('reads the computed value when the token is defined on :root', () => {
    document.documentElement.style.setProperty('--color-rise', '#C0392B');
    document.documentElement.style.setProperty('--accent', '#2563EB');
    expect(resolveChartColor('--color-rise')).toBe('#C0392B');
    expect(resolveChartColor('--accent')).toBe('#2563EB');
    // 显式 fallback 在 token 有定义时不生效
    expect(resolveChartColor('--accent', '#60A5FA')).toBe('#2563EB');
  });
});

describe('resolveChartColors', () => {
  it('resolves each token with per-index fallback semantics', () => {
    document.documentElement.style.setProperty('--text-primary', '#0F1115');
    const out = resolveChartColors(
      ['--text-primary', '#abc', '--color-fall'],
      ['#000001', '#000002', '#000003'],
    );
    expect(out[0]).toBe('#0F1115'); // token 有定义 → 计算值
    expect(out[1]).toBe('#abc'); // 字面量透传
    // token 未定义：resolveChartColors 总是把按索引的显式 fallback
    // 传给 resolveChartColor，显式值优先于内置 DEFAULT_FALLBACKS。
    expect(out[2]).toBe('#000003');
  });
});

describe('subscribeChartThemeCache', () => {
  it('notifies subscribers on themechange and stops after unsubscribe', () => {
    let hits = 0;
    const unsub = subscribeChartThemeCache(() => {
      hits += 1;
    });
    document.dispatchEvent(new Event('themechange'));
    expect(hits).toBe(1);
    unsub();
    document.dispatchEvent(new Event('themechange'));
    expect(hits).toBe(1);
  });
});
