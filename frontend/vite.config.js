import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Locally the API runs on :8000; like Caddy in production, pass /api
// through, so links built from the site's address (e.g. logos) work.
const api = { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } };

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // Libraries change far less often than YGT itself: in their own
        // files, browsers keep them cached from one release to the next.
        // One file: several of them build on React, and split apart they
        // can load before it does.
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom", "@tanstack/react-query", "axios", "i18next", "react-i18next", "sonner"],
        },
      },
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: api,
  },
  preview: {
    proxy: api,
  },
});
