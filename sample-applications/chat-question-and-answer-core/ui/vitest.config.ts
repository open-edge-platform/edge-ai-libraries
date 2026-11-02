// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@carbon/react': '@carbon/react/es',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './vitest.setup.ts',
    server: {
      deps: {
        inline: ['@carbon/react', '@carbon/utilities', 'temporal-polyfill'],
      },
    },
    coverage: {
      provider: 'istanbul',
    },
  },
});
