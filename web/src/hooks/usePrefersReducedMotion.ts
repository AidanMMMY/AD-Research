import { useEffect, useState } from 'react';

/**
 * Apple Design #14 — prefers-reduced-motion.
 *
 * Subscribes to the system "reduce motion" media query so consumers can
 * swap gesture-driven animations (springs, slides, scale) for a static
 * cross-fade (or instant cut) without missing the initial value on mount.
 *
 * SSR-safe: returns `false` on the server / when `window` is absent.
 */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  return reduced;
}