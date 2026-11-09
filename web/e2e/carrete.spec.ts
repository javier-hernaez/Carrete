import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { totp } from "./totp";

const PASSWORD = "una frase larga y segura de prueba";

/** Genera JPEG sintéticos en el propio navegador (nunca fotos reales). */
async function syntheticPhotos(page: Page, names: string[]) {
  const data = await page.evaluate(async (list) => {
    const out: { name: string; b64: string }[] = [];
    for (const [i, name] of list.entries()) {
      const canvas = document.createElement("canvas");
      canvas.width = 640;
      canvas.height = 480;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("sin canvas");
      const grad = ctx.createLinearGradient(0, 0, 640, 480);
      grad.addColorStop(0, `hsl(${i * 70}, 70%, 55%)`);
      grad.addColorStop(1, `hsl(${i * 70 + 140}, 60%, 35%)`);
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, 640, 480);
      ctx.fillStyle = "#fff";
      ctx.font = "64px sans-serif";
      ctx.fillText(String(i + 1), 280, 260);
      const blob = await new Promise<Blob>((ok) => {
        canvas.toBlob((b) => ok(b as Blob), "image/jpeg", 0.85);
      });
      const bytes = new Uint8Array(await blob.arrayBuffer());
      let bin = "";
      bytes.forEach((b) => (bin += String.fromCharCode(b)));
      out.push({ name, b64: btoa(bin) });
    }
    return out;
  }, names);
  return data.map((d) => ({ name: d.name, mimeType: "image/jpeg", buffer: Buffer.from(d.b64, "base64") }));
}

async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
}

test("de la instalación a ver las fotos subidas", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text());
  });

  // Asistente inicial
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Bienvenido a Carrete" })).toBeVisible();
  await expectAccessible(page);
  await page.getByLabel("Código de arranque").fill(process.env.E2E_SETUP_TOKEN ?? "");
  await page.getByLabel("Tu nombre").fill("Javier");
  await page.getByLabel("Usuario").fill("javier");
  await page.getByLabel("Contraseña").fill(PASSWORD);
  await page.getByLabel("Primer espacio").fill("Pareja");
  await page.getByRole("button", { name: "Crear cuenta" }).click();

  // Segundo factor
  await expect(page.getByRole("heading", { name: "Protege tu cuenta" })).toBeVisible();
  await page.getByText("¿No puedes escanearlo?").click();
  const secret = (await page.locator("details p").innerText()).trim();
  await page.getByLabel("Código de 6 cifras").fill(totp(secret));
  await page.getByRole("button", { name: "Activar" }).click();
  await expect(page.getByLabel("Códigos de recuperación")).toBeVisible();
  await page.getByRole("button", { name: "Ya los he guardado" }).click();
  await expect(page.getByRole("heading", { name: "Todavía no hay fotos" })).toBeVisible();
  await expectAccessible(page);

  // Subir
  await page.getByRole("link", { name: "Subir" }).first().click();
  const files = await syntheticPhotos(page, [
    "IMG-20230415-WA0001.jpg",
    "IMG-20230416-WA0002.jpg",
    "IMG-20230416-WA0003.jpg",
  ]);
  await page.getByLabel("Elegir fotos y vídeos").setInputFiles(files);
  await expect(page.getByText("3 subidas, 0 ya estaban, 0 errores")).toBeVisible({ timeout: 90_000 });
  // Volver a subir lo mismo no duplica nada
  await page.getByLabel("Elegir fotos y vídeos").setInputFiles(files.slice(0, 1));
  await expect(page.getByText("3 subidas, 1 ya estaban, 0 errores")).toBeVisible({ timeout: 60_000 });

  // Línea temporal: agrupada por días y con las miniaturas generadas
  await page.getByRole("link", { name: "Fotos" }).first().click();
  await expect(page.getByText("3 elementos")).toBeVisible();
  await expect(page.getByRole("heading", { name: /16 de abril de 2023/ })).toBeVisible();
  await expect(page.getByText("Procesando…")).toHaveCount(0, { timeout: 90_000 });
  const thumbs = page.getByRole("button", { name: /^Foto del/ });
  await expect(thumbs).toHaveCount(3);
  await expect(page.locator("img[src$='/thumb']").first()).toHaveJSProperty("complete", true);
  await expectAccessible(page);

  // Visor
  await thumbs.first().click();
  const viewer = page.getByRole("dialog", { name: "Visor de fotos" });
  await expect(viewer.getByText("1 de 3")).toBeVisible();
  await expect(viewer.locator("img")).toHaveJSProperty("naturalWidth", 640);
  await page.keyboard.press("ArrowRight");
  await expect(viewer.getByText("2 de 3")).toBeVisible();
  await page.keyboard.press("i");
  await expect(viewer.getByText("WhatsApp")).toBeVisible();
  await page.goBack();
  await expect(viewer).toBeHidden();

  expect(consoleErrors.filter((e) => /Content Security Policy|Refused/.test(e))).toEqual([]);
});
