import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      proxy: {
        "/assets/videos": {
          target: "http://localhost:80",
          changeOrigin: true,
          secure: false,
          ws: false,
        },
        "/stream": {
          target: env.VITE_MEDIAMTX_URL || "http://localhost:8889",
          changeOrigin: true,
          secure: false,
          ws: true,
        },
        "/model-download": {
          target: env.VITE_MODEL_DOWNLOAD_URL || "http://localhost:8000",
          changeOrigin: true,
          secure: false,
          ws: false,
          rewrite: (path: string) => path.replace(/^\/model-download/, "/api/v1"),
        },
        "/api": {
          target: env.VITE_API_URL || "http://localhost:7860",
          changeOrigin: true,
          secure: false,
          ws: false,
        },
        "/metrics/ws": {
          target: env.VITE_API_URL || "http://localhost:7860",
          changeOrigin: true,
          secure: false,
          ws: true,
        },
      },
    },
  };
});
