/**
 * Static backdrop for the login page: deep-blue base + a single accent
 * radial glow + bottom vignette, all expressed with theme tokens.
 *
 * Replaces the old sci-fi AuroraBackground (starfield / meteor / scanline
 * layers) — removed in the 2026-07-21 login convergence so the page matches
 * the in-app blue-indigo SaaS theme. No animation, so no reduced-motion
 * handling is needed. Styles live in global.css (.login-backdrop*).
 */
export default function LoginBackdrop() {
  return (
    <div className="login-backdrop" aria-hidden="true">
      <div className="login-backdrop__glow" />
      <div className="login-backdrop__vignette" />
    </div>
  );
}
