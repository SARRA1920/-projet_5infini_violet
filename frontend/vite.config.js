import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = "http://backend:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 3000,
    watch: {
      usePolling: true,
    },
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/health": { target: backend, changeOrigin: true },
      "/auth": { target: backend, changeOrigin: true },
    },
  },
});
