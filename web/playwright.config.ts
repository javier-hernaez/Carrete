import { defineConfig, devices } from "@playwright/test";

/**
 * Prueba de extremo a extremo contra una instancia real de Carrete recién creada (sin cuentas).
 * La levanta deploy/scripts/e2e.sh, que fija el código de arranque en CARRETE_SETUP_TOKEN.
 */
export default defineConfig({
  testDir: "e2e",
  timeout: 180_000,
  expect: { timeout: 30_000 },
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:8011",
    trace: "off",
    screenshot: "only-on-failure",
    locale: "es-ES",
    timezoneId: "Europe/Madrid",
  },
  projects: [{ name: "escritorio", use: { ...devices["Desktop Chrome"] } }],
});
