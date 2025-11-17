// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './vitest.setup.ts',
    coverage: {
      provider: 'istanbul',
      exclude: [
        'src/components/Drawer/**',
        'src/components/Drawer/*',
        '**/src/components/Drawer/**',
        'dist/**',
      ],
    },
  },
});
