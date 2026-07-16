/**
 * Vitest global setup.
 *
 * Imports `@testing-library/jest-dom` so its matchers (e.g. `toBeInTheDocument`)
 * are registered on every test, and registers `jest-axe`'s
 * `toHaveNoViolations` matcher the same way.
 *
 * Keep this file tiny — anything heavier should live in a per-suite setup.
 */
import '@testing-library/jest-dom/vitest';
import { expect } from 'vitest';
import { toHaveNoViolations } from 'jest-axe';

expect.extend(toHaveNoViolations);