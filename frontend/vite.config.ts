import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL ?? "http://localhost:8000",
        changeOrigin: true,
      },
      "/health": {
        target: process.env.VITE_API_URL ?? "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => `/api/v1${path}`,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          query: ["@tanstack/react-query"],
          charts: ["recharts"],
        },
      },
    },
  },
});
