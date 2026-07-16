/**
 * PerformanceIndicator — dev-only floating Web Vitals badge.
 *
 * Mounted by AppLayout only when `import.meta.env.DEV` is true. The
 * badge collapses to a tiny pill showing the latest LCP/INP/CLS; click
 * to expand a panel with the full breakdown (all five metrics + the
 * rating color coding + the page path).
 *
 * This component is purely informational. It never blocks user input
 * and never renders anything in production builds.
 */
import { useEffect, useState } from 'react';
import {
  subscribeWebVitals,
  getLatestVitals,
  type WebVitalsSample,
} from '@/utils/webVitals';

/** Rating → swatch color. Mirrors the web-vitals thresholds. */
const RATING_COLOR: Record<WebVitalsSample['rating'], string> = {
  good: '#30A46C',
  'needs-improvement': '#F0B100',
  poor: '#E5484D',
};

/** Human-friendly unit per metric (CLS is unitless). */
function formatValue(name: WebVitalsSample['name'], value: number): string {
  if (name === 'CLS') return value.toFixed(3);
  return `${value.toFixed(0)} ms`;
}

/** Order shown in the panel — Core Web Vitals first, then supporting. */
const DISPLAY_ORDER: WebVitalsSample['name'][] = [
  'LCP',
  'INP',
  'CLS',
  'FCP',
  'TTFB',
];

export default function PerformanceIndicator() {
  const [samples, setSamples] = useState<WebVitalsSample[]>(() =>
    getLatestVitals(),
  );
  const [open, setOpen] = useState(false);

  useEffect(() => {
    return subscribeWebVitals((sample) => {
      setSamples((prev) => {
        // Keep one entry per metric name, replace on update.
        const next = prev.filter((s) => s.name !== sample.name);
        next.push(sample);
        return next;
      });
    });
  }, []);

  // Stable lookup map.
  const byName = new Map(samples.map((s) => [s.name, s]));
  const lcp = byName.get('LCP');
  const inp = byName.get('INP');
  const cls = byName.get('CLS');

  const summary = [lcp, inp, cls].filter(Boolean) as WebVitalsSample[];
  const worstRating: WebVitalsSample['rating'] | null = summary.length
    ? (['poor', 'needs-improvement', 'good'].find((r) =>
        summary.some((s) => s.rating === r),
      ) as WebVitalsSample['rating']) ?? null
    : null;
  const badgeBg = worstRating ? RATING_COLOR[worstRating] : '#5B6778';

  return (
    <>
      {/* Badge — fixed bottom-right, 12px inset per spec. */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={
          open
            ? '隐藏 Web Vitals 面板'
            : '显示 Web Vitals 面板（仅 dev 模式可见）'
        }
        aria-label="切换 Web Vitals 面板"
        aria-expanded={open}
        style={{
          position: 'fixed',
          bottom: 12,
          right: 12,
          zIndex: 9999,
          padding: '6px 10px',
          borderRadius: 999,
          border: 'none',
          background: badgeBg,
          color: '#fff',
          fontFamily:
            'var(--font-mono, "JetBrains Mono", "SF Mono", monospace)',
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: 0.3,
          cursor: 'pointer',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.25)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          transition: 'background 200ms ease',
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 6,
            height: 6,
            borderRadius: 999,
            background: '#fff',
            opacity: 0.85,
          }}
        />
        <span>
          {summary.length === 0
            ? '等待指标…'
            : summary
                .map((s) => `${s.name} ${formatValue(s.name, s.value)}`)
                .join(' · ')}
        </span>
      </button>

      {/* Panel — same anchor as the badge, expands upward. */}
      {open && (
        <div
          role="dialog"
          aria-label="Web Vitals 面板"
          style={{
            position: 'fixed',
            bottom: 56,
            right: 12,
            zIndex: 9999,
            width: 320,
            maxHeight: '70vh',
            overflow: 'auto',
            background: 'var(--card-bg, #fff)',
            color: 'var(--text-primary, #0F1115)',
            border: '1px solid var(--border-default, #e5e7eb)',
            borderRadius: 12,
            boxShadow: '0 12px 32px rgba(0, 0, 0, 0.18)',
            padding: 16,
            fontFamily:
              'var(--font-sans, Inter, -apple-system, "PingFang SC", sans-serif)',
            fontSize: 13,
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 12,
            }}
          >
            <div style={{ fontWeight: 600 }}>Web Vitals</div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="关闭"
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-tertiary, #8894A4)',
                cursor: 'pointer',
                fontSize: 16,
                lineHeight: 1,
              }}
            >
              ×
            </button>
          </div>

          <div
            style={{
              fontSize: 11,
              color: 'var(--text-tertiary, #8894A4)',
              marginBottom: 12,
              wordBreak: 'break-all',
            }}
          >
            {typeof window !== 'undefined' ? window.location.pathname : '/'}
          </div>

          <div style={{ display: 'grid', gap: 8 }}>
            {DISPLAY_ORDER.map((name) => {
              const s = byName.get(name);
              return (
                <div
                  key={name}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 10px',
                    borderRadius: 8,
                    background: 'var(--bg-elevated, #F3F5F7)',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                    }}
                  >
                    <span
                      aria-hidden="true"
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: 999,
                        background: s ? RATING_COLOR[s.rating] : '#C5CBD3',
                      }}
                    />
                    <span style={{ fontWeight: 500 }}>{name}</span>
                  </div>
                  <div
                    style={{
                      fontFamily:
                        'var(--font-mono, "JetBrains Mono", monospace)',
                      fontSize: 12,
                      color: 'var(--text-secondary, #5B6778)',
                    }}
                  >
                    {s ? formatValue(name, s.value) : '—'}
                  </div>
                </div>
              );
            })}
          </div>

          <div
            style={{
              marginTop: 12,
              fontSize: 11,
              color: 'var(--text-tertiary, #8894A4)',
            }}
          >
            绿=良好 / 黄=需改进 / 红=差 · 数据通过
            <code style={{ marginLeft: 4 }}>POST /api/v1/stats/web-vitals</code>
            {' '}上报
          </div>
        </div>
      )}
    </>
  );
}