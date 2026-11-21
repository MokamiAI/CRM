import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { OG_IMAGE, PAGES, SITE_URL } from "./src/seo/pages.js";

const escape = (s) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/** The head tags for one public page: title, description, canonical
 *  address and the link-preview (Open Graph / Twitter) card. */
function metaTags(path) {
  const page = PAGES[path];
  const url = SITE_URL + (path === "/" ? "/" : path);
  const ogTitle = escape(page.ogTitle ?? page.title);
  const ogDescription = escape(page.ogDescription ?? page.description);
  return [
    `<title>${escape(page.title)}</title>`,
    `<meta name="description" content="${escape(page.description)}" />`,
    page.noindex ? `<meta name="robots" content="noindex" />` : `<link rel="canonical" href="${url}" />`,
    `<meta property="og:site_name" content="YGT" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:locale" content="en_ZA" />`,
    `<meta property="og:url" content="${url}" />`,
    `<meta property="og:title" content="${ogTitle}" />`,
    `<meta property="og:description" content="${ogDescription}" />`,
    `<meta property="og:image" content="${OG_IMAGE}" />`,
    `<meta property="og:image:width" content="1200" />`,
    `<meta property="og:image:height" content="630" />`,
    `<meta property="og:image:alt" content="YGT, You Got This: quotes, invoices and payment reminders in one place" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
  ].join(NL);
}

const MARKER = "<!-- page-meta -->";
const NL = "\n    "; // a new line at the head's indent

/** Every public page gets its own HTML file (dist/about.html, ...): the
 *  same app, with that page's title and preview tags in the head, so a
 *  link shared on WhatsApp shows the right card. Caddy serves
 *  {path}.html before falling back to index.html. */
function pageMetaPlugin() {
  let outDir = "dist";
  return {
    name: "ygt-page-meta",
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
    },
    // The home page's tags (also in development).
    transformIndexHtml: (html) => html.replace(MARKER, MARKER + NL + metaTags("/")),
    closeBundle() {
      const home = readFileSync(resolve(outDir, "index.html"), "utf8");
      const start = home.indexOf(MARKER);
      const end = home.indexOf("<meta name=\"twitter:card\"", start);
      if (start < 0 || end < 0) throw new Error("page-meta: marker not found in dist/index.html");
      const tail = home.indexOf("/>", end) + 2;
      for (const path of Object.keys(PAGES)) {
        if (path === "/") continue;
        const html = home.slice(0, start) + MARKER + NL + metaTags(path) + home.slice(tail);
        writeFileSync(resolve(outDir, `${path.slice(1)}.html`), html);
      }
    },
  };
}

// Locally the API runs on :8000; like Caddy in production, pass /api
// through, so links built from the site's address (e.g. logos) work.
const api = { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } };

export default defineConfig({
  plugins: [react(), pageMetaPlugin()],
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
