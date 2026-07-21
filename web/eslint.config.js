/**
 * ESLint flat config — Phase 7c (2026-07-16).
 *
 * Adds the ``jsx-a11y`` plugin so every PR is linted against the
 * WCAG 2.1 structural rules that don't depend on layout (anchor-is-valid,
 * click-events-have-key-events, no-static-element-interactions). The
 * complement to this lint pass is the axe-core smoke test in
 * ``tests/a11y/smoke.test.tsx``, which catches runtime violations on
 * the rendered DOM.
 *
 * The repo had no prior ESLint config; this file is the single source
 * of truth for linting the web app. ``eslint --max-warnings=0`` is
 * wired into ``npm run lint`` (see ``package.json``).
 */
import js from '@eslint/js';
import tsParser from '@typescript-eslint/parser';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import reactHooks from 'eslint-plugin-react-hooks';

export default [
  {
    ignores: ['dist/**', 'node_modules/**', 'coverage/**', 'screenshots/**'],
  },
  js.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}', 'tests/**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
        ecmaFeatures: { jsx: true },
        project: './tsconfig.json',
        tsconfigRootDir: import.meta.dirname,
      },
      globals: {
        // Browser + DOM globals that the source code touches but that
        // ESLint 9 doesn't auto-fill in for an app written in TypeScript.
        // Keep this list tight — anything missing here shows up as a
        // "no-undef" error during lint.
        window: 'readonly',
        document: 'readonly',
        navigator: 'readonly',
        matchMedia: 'readonly',
        localStorage: 'readonly',
        sessionStorage: 'readonly',
        location: 'readonly',
        history: 'readonly',
        HTMLElement: 'readonly',
        HTMLDivElement: 'readonly',
        HTMLButtonElement: 'readonly',
        HTMLAnchorElement: 'readonly',
        HTMLInputElement: 'readonly',
        HTMLSpanElement: 'readonly',
        Element: 'readonly',
        Node: 'readonly',
        KeyboardEvent: 'readonly',
        MouseEvent: 'readonly',
        CustomEvent: 'readonly',
        Event: 'readonly',
        MessageEvent: 'readonly',
        NodeJS: 'readonly',
        console: 'readonly',
        fetch: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        requestAnimationFrame: 'readonly',
        cancelAnimationFrame: 'readonly',
        queueMicrotask: 'readonly',
        process: 'readonly',
        global: 'readonly',
        __dirname: 'readonly',
        __filename: 'readonly',
        import: 'readonly',
        export: 'readonly',
      },
    },
    plugins: {
      'jsx-a11y': jsxA11y,
      'react-hooks': reactHooks,
    },
    rules: {
      ...jsxA11y.configs.recommended.rules,
      // react-hooks v7 ships a flat config export under
      // ``reactHooks.configs.recommended``. Apply it so pre-existing
      // ``// eslint-disable-next-line react-hooks/exhaustive-deps``
      // comments in source files resolve to a real rule instead of
      // throwing "Definition for rule ... was not found".
      //
      // Every rule in the recommended config is downgraded to ``warn``
      // — these are real issues, but the codebase has never been linted
      // against them and CI shouldn't break on day one. After the
      // backlog is clean they should graduate to ``error``.
      ...Object.fromEntries(
        Object.keys(reactHooks.configs.recommended.rules || {}).map(
          (rule) => [rule, 'warn']
        )
      ),
      // TypeScript already reports missing/unused bindings via its own
      // checker. ESLint's built-ins fight with the type checker and
      // produce noise (e.g. unused callback parameters, ``unknown``
      // catch bindings). Disable them — the type system has our back.
      'no-undef': 'off',
      'no-unused-vars': 'off',
      'no-empty': ['warn', { allowEmptyCatch: true }],
      // Phase 7c: warn (not error) so we get green CI while sweeping
      // pre-existing violations. Once the backlog is clean these should
      // graduate to 'error' to enforce regression prevention.
      'jsx-a11y/anchor-is-valid': 'warn',
      'jsx-a11y/click-events-have-key-events': 'warn',
      'jsx-a11y/no-static-element-interactions': 'warn',
    },
  },
  {
    // Design-system gate (2026-07-21): pages must not import the raw
    // antd Card / Empty / Skeleton — use the tokenized wrappers so the
    // dual-theme tokens in theme.css stay the single source of truth.
    // Migration guide:
    //   Card     -> @/components/Panel
    //   Empty    -> @/components/EmptyState
    //   Skeleton -> @/components/LoadingBlock
    // Genuine exceptions (e.g. Skeleton.Input / Skeleton.Button inline
    // control-shaped placeholders that LoadingBlock does not cover) may
    // keep the antd import with an eslint-disable comment stating why.
    files: ['src/pages/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: 'antd',
              importNames: ['Card', 'Empty', 'Skeleton'],
              message:
                'pages 层请迁移到设计系统组件：Card → @/components/Panel，Empty → @/components/EmptyState，Skeleton → @/components/LoadingBlock。确属例外的场景用 eslint-disable 注释说明原因。',
            },
          ],
        },
      ],
    },
  },
  {
    // Test files deliberately attach onClick handlers to generic divs
    // to assert on the exact DOM shape of the production component.
    //
    // ``tsconfig.json`` only includes ``src/``, so we drop the
    // ``parserOptions.project`` requirement for tests — without this the
    // parser refuses to load the file and emits a hard parse error.
    files: ['tests/**/*.{ts,tsx}'],
    languageOptions: {
      parserOptions: {
        project: null,
      },
    },
    rules: {
      'jsx-a11y/no-static-element-interactions': 'off',
      'jsx-a11y/click-events-have-key-events': 'off',
    },
  },
  {
    // Vitest / Vite configs are plain TS, no React. Trim jsx-a11y
    // surface so ESLint doesn't flag global helpers.
    files: ['vitest.config.ts', 'vite.config.ts'],
    rules: {
      'jsx-a11y/anchor-is-valid': 'off',
      'jsx-a11y/click-events-have-key-events': 'off',
      'jsx-a11y/no-static-element-interactions': 'off',
    },
  },
];