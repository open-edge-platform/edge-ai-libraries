// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Flat ESLint config (ESLint 9+) for a Vite + React 19 + JavaScript (JSX)
// app. Was missing from this template even though package.json ships
// `eslint` + a `lint` script — without this file `npm run lint` fails
// outright for every app scaffolded from this template. Keep in sync with
// the react-redux-plain-css template's equivalent config (Stack B has the
// same gap/fix, TypeScript flavor).

import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';

export default [
  { ignores: ['dist'] },
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: 'module',
      globals: globals.browser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...js.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
  {
    // Node-context config files (vite.config.js, etc.) run outside the
    // browser and reference `process`/`__dirname` — without this override
    // `npm run lint` fails on every template's own vite.config.js.
    files: ['*.config.js'],
    languageOptions: {
      globals: globals.node,
    },
  },
];
