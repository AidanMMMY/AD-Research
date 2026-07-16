import { useEffect } from 'react';
import type { CSSProperties } from 'react';
import { usePrefersReducedMotion } from './usePrefersReducedMotion';

/**
 * useChartMotion — single source of truth for the "Apple-style" motion layer
 * that used to live as a ~80-line `ADX_STYLE` string duplicated across Macro,
 * FundFlow, SectorRotation, Futures, GlobalMarkets (and friends).
 *
 * Responsibilities:
 *  1. Inject the shared page-motion stylesheet exactly once (scoped under the
 *     `.adx-motion` wrapper class). Consumers wrap their page in
 *     `<div className="adx-motion">` instead of re-declaring the CSS.
 *  2. Expose `reducedMotion` so JS-driven animations (e.g. ECharts
 *     `animation`) can be disabled to honour `prefers-reduced-motion`.
 *  3. Return `enterProps` / `exitProps` — inline-style spring configs for a
 *     panel that materializes / dematerializes (chart panels). These are
 *     framer-motion-shaped (`initial` / `animate` / `transition` / `exit`) but
 *     applied as plain inline styles + CSS transitions, so no animation
 *     dependency is required. When the user prefers reduced motion the spring
 *     collapses to a plain cross-fade (transforms disabled).
 *
 * This is a pure hook — it returns data and runs a CSS-injection side effect,
 * but renders no JSX. Callers own the markup.
 */

const STYLE_ID = 'adx-chart-motion';

/**
 * The shared stylesheet. Scoped under `.adx-motion` so it only affects pages
 * that opt in. `--adx-spring` can be overridden per page via an inline style
 * (GlobalMarkets uses a bouncier overshoot curve, for example).
 */
const MOTION_CSS = `
.adx-motion {
  /* Critically-damped monotonic spring (Apple-style, no overshoot). */
  --adx-spring: cubic-bezier(0.32, 0.72, 0, 1);
  --adx-ease-out: cubic-bezier(0.22, 0.9, 0.3, 1);
}
.adx-motion .ant-btn,
.adx-motion .ad-news-events-list__item {
  touch-action: manipulation;
  transition: transform 240ms var(--adx-spring), background-color 140ms var(--adx-ease-out);
}
.adx-motion .ant-btn:active,
.adx-motion .ad-news-events-list__item:active {
  transform: scale(0.97);
  transition-duration: 0ms;
}
.adx-motion .ant-segmented-item,
.adx-motion .ant-tabs-tab {
  touch-action: manipulation;
  transition: color 140ms var(--adx-ease-out);
}
.adx-motion .ant-select-selector {
  transition: border-color 140ms var(--adx-ease-out), box-shadow 140ms var(--adx-ease-out);
}
.adx-motion .ant-table-tbody > tr {
  touch-action: manipulation;
  transition: background-color 140ms var(--adx-ease-out);
}
.adx-motion .ant-table-tbody > tr:active {
  background-color: var(--bg-active);
  transition-duration: 0ms;
}
.adx-motion h1,
.adx-motion h2,
.adx-motion .ant-typography h1,
.adx-motion .ant-typography h2 {
  letter-spacing: -0.02em;
  line-height: 1.18;
}
.adx-motion .ad-text-xs,
.adx-motion .ad-text-small {
  letter-spacing: 0.01em;
}
@media (prefers-reduced-motion: reduce) {
  .adx-motion *,
  .adx-motion *::before,
  .adx-motion *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
  .adx-motion .ant-btn:active,
  .adx-motion .ad-news-events-list__item:active {
    transform: none;
  }
}
`;

function ensureStyleInjected(): void {
  if (typeof document === 'undefined') return;
  if (document.getElementById(STYLE_ID)) return;
  const el = document.createElement('style');
  el.id = STYLE_ID;
  el.textContent = MOTION_CSS;
  document.head.appendChild(el);
}

export interface ChartMotion {
  /** Whether the user has requested reduced motion (system setting). */
  reducedMotion: boolean;
  /** Inline-style spring config for a panel entering / materializing. */
  enterProps: {
    initial: CSSProperties;
    animate: CSSProperties;
    transition: CSSProperties;
  };
  /** Inline-style spring config for a panel leaving / dematerializing. */
  exitProps: {
    exit: CSSProperties;
  };
}

const ENTER_TRANSFORM = 'translateY(8px) scale(0.98)';
const REST_TRANSFORM = 'translateY(0) scale(1)';

export function useChartMotion(): ChartMotion {
  const reducedMotion = usePrefersReducedMotion();

  // Inject the shared stylesheet once. Runs client-side only.
  useEffect(() => {
    ensureStyleInjected();
  }, []);

  if (reducedMotion) {
    // Cross-fade only — transforms disabled per Apple Design #14.
    return {
      reducedMotion,
      enterProps: {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        transition: { transition: 'opacity 0.001ms linear' },
      },
      exitProps: {
        exit: { opacity: 0, transition: 'opacity 0.001ms linear' },
      },
    };
  }

  return {
    reducedMotion,
    enterProps: {
      initial: { opacity: 0, transform: ENTER_TRANSFORM },
      animate: { opacity: 1, transform: REST_TRANSFORM },
      transition: {
        transition:
          'transform 320ms var(--adx-spring, cubic-bezier(0.32, 0.72, 0, 1)), opacity 320ms var(--adx-spring, cubic-bezier(0.32, 0.72, 0, 1))',
      },
    },
    exitProps: {
      exit: {
        opacity: 0,
        transform: ENTER_TRANSFORM,
        transition:
          'transform 220ms var(--adx-spring, cubic-bezier(0.32, 0.72, 0, 1)), opacity 220ms var(--adx-spring, cubic-bezier(0.32, 0.72, 0, 1))',
      },
    },
  };
}
