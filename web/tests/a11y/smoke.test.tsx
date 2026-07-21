/**
 * A11y smoke tests — Phase 7c (2026-07-16).
 *
 * Goal: catch gross WCAG 2.1 AA violations in the small set of components
 * that ship the bulk of the platform's interactive surface area.
 *
 * Test inventory
 * --------------
 *  1. ``AppLayout``  — the app shell (sidebar / header / main / footer)
 *                      with every heavy child dependency stubbed.
 *  2. ``StatCard``   — KPI tile in its clickable + non-clickable variants.
 *  3. ``NewsRow``    — the dashboard's compact news row (mirrors the inline
 *                      helper inside ``pages/Dashboard/index.tsx``).
 *  4. ``PerformanceIndicator`` — dev-only Web Vitals badge; ``axe`` runs
 *                      only on the badge itself since the panel is closed
 *                      by default.
 *
 * Constraints
 * -----------
 *  • All tests run in jsdom — no real timers, no I/O, < 30s wall clock.
 *  • Imports are mocked at the module boundary via ``vi.mock`` so we never
 *    reach into the network, the router, or the persisted Zustand stores.
 *  • We do not assert on text content (i18n is in flux). Only structural
 *    a11y rules from axe-core are checked.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render } from '@testing-library/react';
import axeCore, { type Result as AxeResult } from 'axe-core';

/* --------------------------------------------------------------------
 * Shared mocks — declared at the top so every suite below picks them up.
 * ------------------------------------------------------------------ */

/* Every child component used by AppLayout is heavyweight (zustand
 * stores, react-router, tour/palette overlays). Stubbing them as
 * pass-through divs keeps the test focused on the shell's landmark
 * structure and keyboard-handler shape.
 *
 * Note: ``PerformanceIndicator`` is *not* mocked here — it has its own
 * dedicated test suite below, and we'd otherwise replace the real
 * component with a no-op stub for the AppLayout render as well. The
 * actual component is harmless in jsdom once ``utils/webVitals`` is
 * stubbed. */
vi.mock('@/components/OnboardingTour', () => ({
  default: () => null,
}));
vi.mock('@/components/CommandPalette', () => ({
  default: () => null,
}));

/* Router: AppLayout uses useNavigate/useLocation/Outlet. */
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom'
  );
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useLocation: () => ({ pathname: '/dashboard', search: '', hash: '', state: null }),
    Outlet: () => null,
  };
});

/* Stores: AppLayout reads auth + settings. Stub the store hooks with
 * sane defaults; tests never inspect the values, only the shell markup. */
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    user: { id: 1, username: 'tester', role: 'user' },
    logout: vi.fn(),
  }),
}));
vi.mock('@/stores/settings', () => ({
  useSettingsStore: () => ({
    colorConvention: 'china',
    mode: 'novice',
    learningMode: true,
    density: 'comfortable',
    crtEffect: false,
    setColorConvention: vi.fn(),
    setMode: vi.fn(),
    setLearningMode: vi.fn(),
    setDensity: vi.fn(),
    setCrtEffect: vi.fn(),
  }),
}));

/* Hooks: useTheme / useBreakpoint / useFocusRestore would otherwise pull
 * in matchMedia + DOM event listeners we don't exercise here. */
vi.mock('@/hooks/useTheme', () => ({
  useTheme: () => ({
    theme: 'dark',
    setTheme: vi.fn(),
    effectiveTheme: 'dark',
    systemPreference: 'light',
  }),
}));
vi.mock('@/hooks/useBreakpoint', () => ({
  useIsMobile: () => false,
}));
vi.mock('@/hooks/useFocusRestore', () => ({
  useFocusRestore: vi.fn(),
}));

/* PerformanceIndicator reads from ``utils/webVitals``. The component
 * reads the initial snapshot synchronously via ``getLatestVitals`` and
 * subscribes via ``subscribeWebVitals``. We return empty arrays and a
 * no-op unsubscribe so the badge renders without Web Vitals data. */
vi.mock('@/utils/webVitals', () => ({
  subscribeWebVitals: () => () => undefined,
  getLatestVitals: () => [],
}));

/* --------------------------------------------------------------------
 * Helpers
 * ------------------------------------------------------------------ */

async function runAxe(container: Element): Promise<AxeResult> {
  // Run only WCAG 2 A/AA rule tags — the full WCAG 2.1 AAA set fires
  // false positives in jsdom (no real layout / fonts).
  // axe-core v4 ships as a CommonJS module exporting the namespace as
  // ``module.exports = axe``; under vitest's interop it lands on the
  // default property, so we resolve both shapes defensively.
  const axeNs = (axeCore as unknown as { run?: typeof axeCore.run }).run
    ? (axeCore as unknown as { run: typeof axeCore.run })
    : (axeCore as unknown as { default: { run: typeof axeCore.run } }).default;
  return axeNs.run(container, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] },
    rules: {
      // Color contrast needs real layout — skip in jsdom.
      'color-contrast': { enabled: false },
    },
  });
}

/* --------------------------------------------------------------------
 * Tests
 * ------------------------------------------------------------------ */

describe('AppLayout a11y smoke', () => {
  it('renders the app shell landmarks without violations', async () => {
    const AppLayout = (await import('@/components/AppLayout')).default;
    const { container } = render(<AppLayout />);
    // Sanity-check the shell rendered — sidebar nav + main landmark.
    expect(container.querySelector('nav[aria-label="主导航"]')).not.toBeNull();
    expect(container.querySelector('main')).not.toBeNull();
    const results = await runAxe(container);
    expect(results).toHaveNoViolations();
  });
});

describe('StatCard a11y smoke', () => {
  it('renders the non-clickable variant without violations', async () => {
    const StatCard = (await import('@/components/StatCard')).default;
    const { container } = render(
      <StatCard title="收盘价" value="1.234" suffix="USD" />
    );
    // Non-clickable: no role="button", no tabIndex.
    const root = container.firstElementChild as HTMLElement;
    expect(root.getAttribute('role')).toBeNull();
    expect(resultsAria(root, 'aria-label')).toBeNull();
    const results = await runAxe(container);
    expect(results).toHaveNoViolations();
  });

  it('renders the clickable variant without violations', async () => {
    const StatCard = (await import('@/components/StatCard')).default;
    const onClick = vi.fn();
    const { container } = render(
      <StatCard title="成交额" value="2.1B" suffix="¥" onClick={onClick} />
    );
    const root = container.firstElementChild as HTMLElement;
    // Clickable variant: must expose role=button + tabIndex=0 + aria-label.
    expect(root.getAttribute('role')).toBe('button');
    expect(root.getAttribute('tabindex')).toBe('0');
    expect(root.getAttribute('aria-label')).toBe('成交额: 2.1B');
    const results = await runAxe(container);
    expect(results).toHaveNoViolations();
  });
});

describe('NewsRow a11y smoke', () => {
  /* The production ``NewsRow`` is a non-exported helper inside
   * ``pages/Dashboard/index.tsx``. We re-create the same DOM contract
   * here so we can assert on its a11y shape (``role=button``,
   * ``tabIndex=0``, ``aria-label``, keyboard handlers) without
   * pulling the entire Dashboard page (and its 30+ hooks) into jsdom.
   * If the production shape ever drifts from this snapshot the rule
   * "click-events-have-key-events" will fire on it via the lint job. */
  function NewsRowMock({
    article,
    onOpen,
  }: {
    article: { id: number; title: string; source: string; published_at: string };
    onOpen: (id: number) => void;
  }) {
    const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onOpen(article.id);
      }
    };
    return (
      <div
        role="button"
        tabIndex={0}
        aria-label={`${article.title} — 查看新闻详情`}
        onClick={() => onOpen(article.id)}
        onKeyDown={handleKeyDown}
      >
        <span>{article.source}</span>
        <span>{article.title}</span>
      </div>
    );
  }

  it('renders without violations using mock data', async () => {
    const article = {
      id: 42,
      title: '美联储释放鸽派信号，科技股领涨',
      source: '新浪财经',
      published_at: '2026-07-16T01:23:45Z',
    };
    const { container } = render(<NewsRowMock article={article} onOpen={vi.fn()} />);
    const results = await runAxe(container);
    expect(results).toHaveNoViolations();
  });
});

describe('PerformanceIndicator a11y smoke', () => {
  it('renders the dev-only Web Vitals badge without violations', async () => {
    const PerformanceIndicator = (await import('@/components/PerformanceIndicator'))
      .default;
    const { container } = render(<PerformanceIndicator />);
    // Badge must announce itself to assistive tech.
    const button = container.querySelector('button[aria-label="切换 Web Vitals 面板"]');
    expect(button).not.toBeNull();
    expect(button?.getAttribute('aria-expanded')).toBe('false');
    const results = await runAxe(container);
    expect(results).toHaveNoViolations();
  });
});

/* --------------------------------------------------------------------
 * Local helpers
 * ------------------------------------------------------------------ */

/** Tiny wrapper that returns ``getAttribute(name)`` or ``null``. */
function resultsAria(el: HTMLElement, name: string): string | null {
  return el.getAttribute(name);
}