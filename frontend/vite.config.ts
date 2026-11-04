import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the Vite server proxies /api to the FastAPI backend, so the
// browser talks to a single origin exactly like it does behind nginx in Docker.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "node",
  },
});
