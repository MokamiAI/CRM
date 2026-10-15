import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Locally the API runs on :8000; like Caddy in production, pass /api
// through, so links built from the site's address (e.g. logos) work.
const api = { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } };

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: api,
  },
  preview: {
    proxy: api,
  },
});
