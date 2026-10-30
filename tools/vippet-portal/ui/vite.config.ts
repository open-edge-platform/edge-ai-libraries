import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        "@": path.resolve(import.meta.dirname, "./src"),
      },
    },
    build: {
      // Served directly by the portal backend in production.
      outDir: "../server/static",
      emptyOutDir: true,
    },
    server: {
      proxy: {
        "/api": {
          target: env.VITE_PORTAL_API_URL || "http://127.0.0.1:8765",
          changeOrigin: true,
          secure: false,
        },
      },
    },
  };
});
