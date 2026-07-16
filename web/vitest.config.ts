/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

/**
 * Vitest config — Phase 7c (2026-07-16).
 *
 * Used solely by the a11y smoke tests under `tests/a11y/`. The harness
 * keeps the build path aligned with `vite.config.ts` (alias `@` → `./src`)
 * so source files import identically in dev, build, and test.
 *
 * We deliberately use `jsdom` (not `happy-dom`) because axe-core is
 * tested against jsdom and several of the more nuanced color-contrast
 * rules only resolve correctly under jsdom's CSSOM.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
    css: false,
    pool: 'threads',
    testTimeout: 15_000,
    hookTimeout: 15_000,
  },
});