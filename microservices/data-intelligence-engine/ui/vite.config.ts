// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import vue from "@vitejs/plugin-vue";
import { resolve } from "node:path";
import AutoImport from "unplugin-auto-import/vite";
import { AntDesignVueResolver } from "unplugin-vue-components/resolvers";
import Components from "unplugin-vue-components/vite";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target =
    env.DI_ENGINE_PROXY_TARGET ||
    `http://${env.DI_PROXY_HOST || "localhost"}:16022`;
  return {
    base: "/console/",
    plugins: [
      vue(),
      AutoImport({
        imports: ["vue", "vue-router", "pinia"],
        dts: "src/auto-imports.d.ts",
        resolvers: [AntDesignVueResolver()],
      }),
      Components({
        dts: "src/components.d.ts",
        directoryAsNamespace: true,
        resolvers: [AntDesignVueResolver({ importStyle: false })],
      }),
    ],
    resolve: {
      alias: {
        "@": resolve(__dirname, "src"),
        "vue-i18n": "vue-i18n/dist/vue-i18n.cjs.js",
      },
    },
    server: {
      host: "0.0.0.0",
      port: 7778,
      strictPort: true,
      proxy: {
        "/v1/": { target, changeOrigin: true },
        "/health": { target, changeOrigin: true },
      },
    },
    build: {
      outDir: "dist",
      chunkSizeWarningLimit: 1500,
    },
    css: {
      preprocessorOptions: {
        less: {
          javascriptEnabled: true,
          additionalData: `@import "${resolve(__dirname, "src/theme/index.less")}";`,
        },
      },
    },
  };
});
