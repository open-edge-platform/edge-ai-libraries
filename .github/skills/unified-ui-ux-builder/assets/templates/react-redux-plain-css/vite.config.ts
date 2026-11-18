// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// No path aliases here — stack B uses relative imports throughout, matching
// the reference app (education-ai-suite/smart-classroom/ui).
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Point this at the app's backend during local development (see .env.example).
const API_BASE = process.env.VITE_API_BASE || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: API_BASE,
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
