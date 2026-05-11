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
          target: env.VITE_API_URL || "http://localhost",
          changeOrigin: true,
          secure: false,
          ws: false,
        },
        "/assets/images": {
          target: env.VITE_API_URL || "http://localhost",
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
        "/api/v1/metrics": {
          target: env.VITE_METRICS_URL || "http://localhost:9090",
          changeOrigin: true,
          secure: false,
          ws: false,
        },
        "/model-download": {
          target: env.VITE_MODEL_DOWNLOAD_URL || "http://localhost:8000",
          changeOrigin: true,
          secure: false,
          ws: false,
        },
        "/api": {
          target: env.VITE_API_URL || "http://localhost:7860",
          changeOrigin: true,
          secure: false,
          ws: false,
          configure: (proxy) => {
            // Disable response buffering so SSE events stream through immediately
            proxy.on("proxyRes", (proxyRes) => {
              const url = proxyRes.req?.path ?? "";
              if (url.includes("/stream")) {
                proxyRes.headers["cache-control"] = "no-cache";
                proxyRes.headers["x-accel-buffering"] = "no";
              }
            });
          },
        },
        "/metrics/stream": {
          target: env.VITE_METRICS_URL || "http://localhost:9090",
          changeOrigin: true,
          secure: false,
          ws: false,
          configure: (proxy) => {
            // Disable response buffering so SSE events stream through immediately
            proxy.on("proxyRes", (proxyRes) => {
              proxyRes.headers["cache-control"] = "no-cache";
              proxyRes.headers["x-accel-buffering"] = "no";
            });
          },
        },
      },
    },
  };
});
