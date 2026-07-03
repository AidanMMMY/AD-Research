import { useEffect, useState } from 'react';

/**
 * Immersive aurora background for the sci-fi login page.
 *
 * Renders layered radial gradients that slowly drift and breathe, plus a
 * sparse starfield and faint scan lines. The entire animation is CSS-driven
 * for performance; it is disabled when the user prefers reduced motion.
 */
export default function AuroraBackground() {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReducedMotion(mq.matches);

    const handler = (event: MediaQueryListEvent) => {
      setReducedMotion(event.matches);
    };

    if (typeof mq.addEventListener === 'function') {
      mq.addEventListener('change', handler);
      return () => mq.removeEventListener('change', handler);
    }
    // Legacy fallback for older Safari versions.
    mq.addListener(handler);
    return () => mq.removeListener(handler);
  }, []);

  return (
    <div className="aurora-background" aria-hidden="true">
      {/* Base dark canvas */}
      <div className="aurora-base" />

      {/* Slow drifting aurora layers */}
      <div
        className="aurora-layer aurora-layer-1"
        style={{ animationPlayState: reducedMotion ? 'paused' : 'running' }}
      />
      <div
        className="aurora-layer aurora-layer-2"
        style={{ animationPlayState: reducedMotion ? 'paused' : 'running' }}
      />
      <div
        className="aurora-layer aurora-layer-3"
        style={{ animationPlayState: reducedMotion ? 'paused' : 'running' }}
      />

      {/* Sparse starfield */}
      <div className="aurora-stars">
        <span className="aurora-star" style={{ top: '18%', left: '12%', animationDelay: '0s' }} />
        <span className="aurora-star" style={{ top: '32%', left: '78%', animationDelay: '1.2s' }} />
        <span className="aurora-star" style={{ top: '64%', left: '22%', animationDelay: '2.4s' }} />
        <span className="aurora-star" style={{ top: '14%', left: '64%', animationDelay: '0.8s' }} />
        <span className="aurora-star" style={{ top: '82%', left: '85%', animationDelay: '3.1s' }} />
        <span className="aurora-star" style={{ top: '48%', left: '45%', animationDelay: '1.8s' }} />
        <span className="aurora-star" style={{ top: '76%', left: '8%', animationDelay: '2.9s' }} />
        <span className="aurora-star" style={{ top: '26%', left: '92%', animationDelay: '0.5s' }} />
      </div>

      {/* Subtle scan lines */}
      <div className="aurora-scanlines" />

      {/* Bottom vignette to keep the card readable */}
      <div className="aurora-vignette" />
    </div>
  );
}
