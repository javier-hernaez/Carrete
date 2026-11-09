/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En desarrollo, la API se sirve aparte (docker compose en 127.0.0.1:8010) y Vite le reenvía /api.
const apiTarget = process.env.CARRETE_API_URL ?? "http://127.0.0.1:8010";

export default defineConfig({
  plugins: [react()],
  build: {
    target: "es2022",
    sourcemap: false,
    // Sin scripts en línea: la CSP del servidor no admite 'unsafe-inline'.
    modulePreload: { polyfill: false },
    assetsInlineLimit: 0,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": apiTarget,
      "/healthz": apiTarget,
      "/readyz": apiTarget,
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "src/main.tsx", "src/api/schema.d.ts"],
      thresholds: { lines: 70, functions: 70, statements: 70, branches: 70 },
    },
  },
});
