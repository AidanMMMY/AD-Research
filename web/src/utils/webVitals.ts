/**
 * Web Vitals reporter — Phase 7c (2026-07-16) instrumentation layer.
 *
 * Goals:
 *   • Subscribe to the modern Core Web Vitals set (LCP / INP / CLS) plus the
 *     supporting FCP / TTFB signals from the `web-vitals` package.
 *   • Mirror each metric to the dev console so we can spot regressions
 *     locally without spinning up a backend.
 *   • POST each metric to `/api/v1/stats/web-vitals` so the platform can
 *     aggregate field performance over time. The POST is fire-and-forget:
 *     a missing backend, a 404, or a network blip must never block the
 *     UI thread or pollute the console with stack traces.
 *   • Expose a tiny in-memory pub/sub so the dev-only `PerformanceIndicator`
 *     can show the latest values without needing React context.
 *
 * This module is safe to import in production: it no-ops when `web-vitals`
 * can't subscribe (e.g. during SSR-style unit tests) and the network call
 * is wrapped to swallow all errors.
 */
import { onCLS, onFCP, onINP, onLCP, onTTFB, type Metric } from 'web-vitals';
import { statsApi } from '@/api/stats';

/* --------------------------------------------------------------------
 * Pub/sub — keeps PerformanceIndicator decoupled from main.tsx so it
 * can mount/unmount freely in dev mode.
 * ------------------------------------------------------------------ */
export interface WebVitalsSample {
  name: Metric['name'];
  value: number;
  rating: Metric['rating'];
  id: string;
  navigationType: Metric['navigationType'];
  page: string;
  /** epoch ms — used by the indicator to show freshness */
  ts: number;
}

type Listener = (sample: WebVitalsSample) => void;

const listeners = new Set<Listener>();
const latestByName: Partial<Record<Metric['name'], WebVitalsSample>> = {};
let started = false;

/** Subscribe to live metric updates. Returns an unsubscribe fn. */
export function subscribeWebVitals(listener: Listener): () => void {
  listeners.add(listener);
  // Replay the most recent sample so the badge doesn't start blank.
  for (const sample of Object.values(latestByName)) {
    if (sample) listener(sample);
  }
  return () => {
    listeners.delete(listener);
  };
}

/** Snapshot of the most recent value per metric, for the panel view. */
export function getLatestVitals(): WebVitalsSample[] {
  return Object.values(latestByName).filter(Boolean) as WebVitalsSample[];
}

function emit(sample: WebVitalsSample) {
  latestByName[sample.name] = sample;
  for (const listener of listeners) {
    try {
      listener(sample);
    } catch (err) {
      // A faulty listener must not poison the rest of the chain.
      // eslint-disable-next-line no-console
      console.warn('[web-vitals] listener threw:', err);
    }
  }
}

/* --------------------------------------------------------------------
 * Fire-and-forget POST.
 *
 * We deliberately don't `await` this in the metric callback — the API
 * helper is built around react-query / axios, which always returns a
 * Promise. Swallowing the rejection keeps LCP/INP/CLS callbacks clean
 * and guarantees we never block user input on telemetry.
 * ------------------------------------------------------------------ */
function reportToBackend(sample: WebVitalsSample) {
  try {
    void statsApi.webVitals(sample).catch((err) => {
      if (import.meta.env.DEV) {
        // In dev we surface the failure so the developer knows the
        // endpoint isn't wired up yet. In prod we stay silent.
        // eslint-disable-next-line no-console
        console.debug('[web-vitals] backend POST failed:', err?.message ?? err);
      }
    });
  } catch (err) {
    // Defensive — statsApi.webVitals() itself is synchronous, but a future
    // refactor (e.g. lazy import) could throw. Don't let it bubble.
    // eslint-disable-next-line no-console
    console.debug('[web-vitals] reporter threw:', err);
  }
}

function handleMetric(metric: Metric) {
  const sample: WebVitalsSample = {
    name: metric.name,
    value: metric.value,
    rating: metric.rating,
    id: metric.id,
    navigationType: metric.navigationType,
    page: typeof window !== 'undefined' ? window.location.pathname : '/',
    ts: Date.now(),
  };

  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.info(
      `[web-vitals] ${metric.name} = ${metric.value.toFixed(1)} (${metric.rating})`,
      sample,
    );
  }

  emit(sample);
  reportToBackend(sample);
}

/* --------------------------------------------------------------------
 * Public entry point — idempotent. Safe to call multiple times; the
 * `started` guard ensures we never register duplicate observers.
 * ------------------------------------------------------------------ */
export function reportWebVitals(): void {
  if (started) return;
  started = true;

  try {
    onLCP(handleMetric);
    onINP(handleMetric);
    onCLS(handleMetric);
    onFCP(handleMetric);
    onTTFB(handleMetric);
  } catch (err) {
    // `web-vitals` calls PerformanceObserver under the hood. If the
    // browser doesn't support it (very old runtimes, jsdom in unit
    // tests) the constructor throws — degrade gracefully.
    // eslint-disable-next-line no-console
    console.debug('[web-vitals] observer unavailable:', err);
    started = false;
  }
}