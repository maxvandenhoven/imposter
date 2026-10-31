import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The API server that `make dev` starts. The dev server forwards the API paths to it
// with the browser's `Host`, since ADK refuses requests whose `Origin` is another host.
const API_TARGET = process.env.IMPOSTER_API_URL ?? "http://127.0.0.1:8000";
const API_PATHS = ["/catalog", "/apps", "/run_sse", "/traces"];

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    proxy: Object.fromEntries(
      API_PATHS.map((apiPath) => [apiPath, { target: API_TARGET }]),
    ),
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: { include: [/index\.css/] },
  },
});
