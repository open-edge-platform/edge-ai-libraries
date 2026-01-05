// Copyright (C) 2024 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from 'path';

// https://vitejs.dev/config/

// Define the alias
const srcPath = path.resolve(process.cwd(), 'src');

export default defineConfig({
  resolve: {
    alias: {
      '@': srcPath,
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        additionalData: `@use "@/styles/styles.scss" as *;`,
      },
    },
  },
  plugins: [react()],
  server: {
    port: 80,
  },
  test: {
    globals: true,
    environment: "jsdom",
  },
  define: {
    "import.meta.env": process.env,
  },
});
