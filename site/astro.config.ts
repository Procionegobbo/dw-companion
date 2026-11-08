import { defineConfig } from "astro/config";

// Dev-only: the Astro dev server proxies /api to the local FastAPI app so the widget's
// same-origin fetch (spec 008 D6) works without CORS. In production, spec 011's single
// container serves both the site and the API from the same origin.
const API_PROXY_TARGET = "http://127.0.0.1:8000";

export default defineConfig({
  output: "static",
  trailingSlash: "always",
  build: {
    format: "directory",
  },
  vite: {
    server: {
      proxy: {
        "/api": {
          target: API_PROXY_TARGET,
          changeOrigin: false,
        },
      },
    },
  },
});
