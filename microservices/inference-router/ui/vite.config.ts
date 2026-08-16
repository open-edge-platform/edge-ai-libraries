// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import vue from "@vitejs/plugin-vue";
import path, { resolve } from "path";
import AutoImport from "unplugin-auto-import/vite";
import { AntDesignVueResolver } from "unplugin-vue-components/resolvers";
import Components from "unplugin-vue-components/vite";
import { defineConfig, loadEnv } from "vite";
import viteCompression from "vite-plugin-compression";

const pathResolve = (dir: string) => {
  return resolve(__dirname, ".", dir);
};

const alias: Record<string, string> = {
  "@": pathResolve("./src/"),
  "vue-i18n": "vue-i18n/dist/vue-i18n.cjs.js",
};

const viteConfig = defineConfig(({ mode }) => {
  return {
    plugins: [
      vue(),
      viteCompression(),
      AutoImport({
        imports: ["vue", "vue-router", "pinia"],
        dts: "src/auto-imports.d.ts",
        resolvers: [AntDesignVueResolver()],
      }),
      Components({
        resolvers: [
          AntDesignVueResolver({
            importStyle: false, // css in js
          }),
        ],
      }),
    ],
    root: process.cwd(),
    resolve: { alias },
    server: {
      host: "0.0.0.0",
      port: 7010,
      strictPort: true,
      hmr: true,
      proxy: {
        "/v1/": {
          target: "http://10.239.154.57:8000",
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: "dist",
      chunkSizeWarningLimit: 1500,
      rollupOptions: {
        output: {
          chunkFileNames: "assets/js/[name]-[hash].js",
          entryFileNames: "assets/js/[name]-[hash].js",
          assetFileNames: "assets/[ext]/[name]-[hash].[ext]",
        },
      },
    },
    css: {
      preprocessorOptions: {
        less: {
          javascriptEnabled: true,
          additionalData: `@import "${path.resolve(__dirname, "src/theme/index.less")}";`,
        },
      },
    },
  };
});

export default viteConfig;
