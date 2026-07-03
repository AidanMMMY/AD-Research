import { useEffect, useMemo, useState } from 'react';

/**
 * Immersive aurora background for the sci-fi login page.
 *
 * Renders layered radial gradients that slowly drift, breathe, and hue-shift,
 * plus a dense starfield with subtle twinkle and an occasional meteor streak.
 * The entire animation is CSS-driven for performance; it is disabled when the
 * user prefers reduced motion.
 *
 * The component keeps the same external API (no props) so other pages that
 * mount <AuroraBackground /> continue to work without change.
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

  // Stable star positions — generated once per mount. Sizes & delays vary so
  // the field feels organic rather than evenly distributed.
  const stars = useMemo(
    () =>
      Array.from({ length: 64 }, (_, i) => {
        const top = (i * 37) % 100;
        const left = (i * 53) % 100;
        // Mix small dim stars with a handful of brighter accent (cyan) ones.
        const accent = i % 7 === 0;
        const sizeBucket = i % 4; // 0..3 -> 1, 1.5, 2, 2.5 px
        const size = [1, 1.5, 2, 2.5][sizeBucket];
        const delay = ((i * 0.37) % 6).toFixed(2);
        const duration = (3 + ((i * 0.71) % 4)).toFixed(2);
        return { id: i, top, left, accent, size, delay, duration };
      }),
    [],
  );

  // 5 occasional meteor streaks. They are positionally fixed but each uses a
  // long animation cycle + heavy delay so only ~0.4 of them are mid-flight at
  // any given moment.
  const meteors = useMemo(
    () =>
      Array.from({ length: 5 }, (_, i) => ({
        id: i,
        startTop: 5 + i * 14,
        startLeft: 15 + ((i * 23) % 60),
        delay: ((i * 3.7) % 14).toFixed(2),
        duration: (6 + ((i * 0.91) % 5)).toFixed(2),
        length: 80 + ((i * 17) % 80),
      })),
    [],
  );

  return (
    <div className="aurora-background" aria-hidden="true">
      {/* Base dark canvas */}
      <div className="aurora-base" />

      {/* Five drifting aurora layers, each with a distinct hue + drift path.
          Kept on the same DOM API (aurora-layer + aurora-layer-N) to avoid
          breaking any consumer that targets these classnames. */}
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
      <div
        className="aurora-layer aurora-layer-4"
        style={{ animationPlayState: reducedMotion ? 'paused' : 'running' }}
      />
      <div
        className="aurora-layer aurora-layer-5"
        style={{ animationPlayState: reducedMotion ? 'paused' : 'running' }}
      />

      {/* Dense starfield with twinkle */}
      <div className="aurora-stars">
        {stars.map((s) => (
          <span
            key={s.id}
            className={
              'aurora-star' + (s.accent ? ' aurora-star--accent' : '')
            }
            style={{
              top: `${s.top}%`,
              left: `${s.left}%`,
              width: `${s.size}px`,
              height: `${s.size}px`,
              animationDelay: `${s.delay}s`,
              animationDuration: `${s.duration}s`,
            }}
          />
        ))}
      </div>

      {/* Meteor shower — periodic streaks falling across the sky. */}
      <div className="aurora-meteors">
        {meteors.map((m) => (
          <span
            key={m.id}
            className="aurora-meteor"
            style={{
              top: `${m.startTop}%`,
              left: `${m.startLeft}%`,
              width: `${m.length}px`,
              animationDelay: `${m.delay}s`,
              animationDuration: `${m.duration}s`,
            }}
          />
        ))}
      </div>

      {/* Subtle scan lines */}
      <div className="aurora-scanlines" />

      {/* Bottom vignette to keep the card readable */}
      <div className="aurora-vignette" />
    </div>
  );
}