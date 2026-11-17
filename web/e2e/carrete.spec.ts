import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { totp } from "./totp";

const PASSWORD = "una frase larga y segura de prueba";

interface PhotoSpec {
  name: string;
  seed: number;
  width?: number;
  height?: number;
  quality?: number;
}

/** Genera JPEG sintéticos en el propio navegador (nunca fotos reales). Misma semilla = misma imagen. */
async function syntheticPhotos(page: Page, specs: PhotoSpec[]) {
  const data = await page.evaluate(async (list) => {
    const out: { name: string; b64: string }[] = [];
    for (const spec of list) {
      const w = spec.width ?? 640;
      const h = spec.height ?? 480;
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("sin canvas");
      const grad = ctx.createLinearGradient(0, 0, w, h);
      grad.addColorStop(0, `hsl(${spec.seed * 70}, 70%, 55%)`);
      grad.addColorStop(1, `hsl(${spec.seed * 70 + 140}, 60%, 35%)`);
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = "#fff";
      ctx.beginPath();
      ctx.arc(w * (0.2 + 0.15 * (spec.seed % 4)), h * 0.5, h * 0.25, 0, Math.PI * 2);
      ctx.fill();
      const blob = await new Promise<Blob>((ok) => {
        canvas.toBlob((b) => ok(b as Blob), "image/jpeg", spec.quality ?? 0.9);
      });
      const bytes = new Uint8Array(await blob.arrayBuffer());
      let bin = "";
      bytes.forEach((b) => (bin += String.fromCharCode(b)));
      out.push({ name: spec.name, b64: btoa(bin) });
    }
    return out;
  }, specs);
  return data.map((d) => ({ name: d.name, mimeType: "image/jpeg", buffer: Buffer.from(d.b64, "base64") }));
}

async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(
    results.violations.map(
      (v) => `${v.id}: ${v.help} → ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
    ),
  ).toEqual([]);
}

test("de la instalación a ordenar las fotos", async ({ page }) => {
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
    { name: "IMG-20230415-WA0001.jpg", seed: 1 },
    { name: "IMG-20230416-WA0002.jpg", seed: 2 },
    { name: "IMG-20230416-WA0003.jpg", seed: 3 },
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

  // Repetidas: la misma foto reenviada «por WhatsApp», más pequeña y peor comprimida
  await page.getByRole("link", { name: "Subir" }).first().click();
  await page.getByRole("button", { name: "Limpiar la lista" }).click();
  const copy = await syntheticPhotos(page, [
    { name: "IMG-20230415-WA0004.jpg", seed: 1, width: 320, height: 240, quality: 0.4 },
  ]);
  await page.getByLabel("Elegir fotos y vídeos").setInputFiles(copy);
  await expect(page.getByText(/^1 subidas, 0 ya estaban, 0 errores$/)).toBeVisible({ timeout: 60_000 });
  const groups = page.getByRole("list", { name: "Grupos de repetidas" });
  // El worker tiene que procesar la copia antes de poder compararla.
  await expect(async () => {
    await page.goto("/repetidas");
    await expect(groups.getByRole("listitem")).toHaveCount(1, { timeout: 3_000 });
  }).toPass({ timeout: 90_000 });
  await expect(groups.getByText("640×480")).toBeVisible();
  await expectAccessible(page);
  await groups.getByRole("button", { name: "Quedarme con la mejor" }).click();
  await expect(page.getByText("Una a la papelera")).toBeVisible();
  await expect(page.getByRole("heading", { name: "No hay repetidas" })).toBeVisible();

  // Revisar en bloque (lo primero que se ve): marcar una y darle «Vale»
  await page.goto("/revisar");
  await expect(page.getByRole("heading", { name: "Revisar" })).toBeVisible();
  const pending = page.getByRole("button", { name: /^Seleccionar: / });
  await expect(pending).toHaveCount(3);
  await expectAccessible(page);
  await pending.nth(0).click();
  await page
    .getByRole("toolbar", { name: "Acciones sobre la selección" })
    .getByRole("button", { name: "Vale" })
    .click();
  await expect(pending).toHaveCount(2);

  // Revisar de una en una: etiqueta nueva con una sugerencia, y luego vale y no vale con el teclado
  await page.getByRole("button", { name: "Una a una" }).click();
  await expect(page.getByText("1 de 2")).toBeVisible();
  await page.getByRole("button", { name: "+ Etiqueta" }).click();
  await page.getByRole("dialog", { name: "Etiquetas" }).getByRole("button", { name: "+ Humor" }).click();
  await expect(page.getByText("Etiqueta «Humor» puesta")).toBeVisible();
  await page.getByRole("dialog", { name: "Etiquetas" }).getByRole("button", { name: "Cerrar" }).click();
  await expect(page.getByRole("button", { name: "✓ Humor" })).toBeVisible();
  await expectAccessible(page);
  await page.keyboard.press("ArrowRight");
  await expect(page.getByText("2 de 2")).toBeVisible();
  await page.keyboard.press("x");
  await expect(page.getByRole("heading", { name: "¡Listo!" })).toBeVisible();
  await expect(page.getByText(/1 valen y 1 descartados/)).toBeVisible();

  // Poner la ubicación a mano y ver el lugar en el visor (geocodificación sin conexión)
  await page.goto("/");
  await expect(page.getByText("2 elementos")).toBeVisible();
  const boxes = page.getByRole("button", { name: /^Seleccionar: / });
  await boxes.nth(0).click({ force: true });
  await page.getByRole("button", { name: "Lugar…" }).click();
  await page.getByLabel("Coordenadas").fill("37.3886, -5.9823");
  await expectAccessible(page);
  await page.getByRole("button", { name: "Guardar" }).click();
  await expect(page.getByText("Ubicación puesta")).toBeVisible();
  await page
    .getByRole("button", { name: /^Foto del/ })
    .first()
    .click();
  await page.keyboard.press("i");
  await expect(
    page.getByRole("dialog", { name: "Visor de fotos" }).getByText(/Sevilla.*España/),
  ).toBeVisible();
  await page.goBack();

  // Un recuerdo al azar encima de la línea temporal; las fichas de etiquetas filtran
  await expect(page.getByText("2 elementos")).toBeVisible();
  await expect(page.getByRole("region", { name: "Un recuerdo al azar" })).toBeVisible();
  const tagChips = page.getByRole("group", { name: "Filtrar por etiqueta" });
  await tagChips.getByRole("button", { name: /Humor/ }).click();
  await expect(page.getByText("1 elemento", { exact: true })).toBeVisible();
  await tagChips.getByRole("button", { name: "Todas" }).click();
  await expect(page.getByText("2 elementos")).toBeVisible();

  // Etiquetar la selección y crear un álbum con ella
  await boxes.nth(0).click({ force: true });
  await boxes.nth(1).click({ force: true });
  await expect(page.getByText("2 seleccionadas")).toBeVisible();
  await page.getByRole("button", { name: "Etiquetas…" }).click();
  await page
    .getByRole("dialog", { name: "Etiquetas de 2" })
    .getByRole("button", { name: "+ Personas" })
    .click();
  await expect(page.getByText("«Personas» puesta a 2")).toBeVisible();
  await page.getByRole("dialog", { name: "Etiquetas de 2" }).getByRole("button", { name: "Cerrar" }).click();
  await page.getByRole("button", { name: "Álbum…" }).click();
  const picker = page.getByRole("dialog", { name: "Añadir 2 a un álbum" });
  await picker.getByLabel("Nuevo álbum").fill("Asturias 2025");
  await picker.getByRole("button", { name: "Crear y añadir" }).click();
  await expect(page.getByText("2 añadidas a «Asturias 2025»")).toBeVisible();
  await page.getByRole("link", { name: "Álbumes" }).first().click();
  await page.getByRole("link", { name: /Asturias 2025\s*2 elementos/ }).click();
  // Dentro del álbum, solo sus etiquetas y su recuento allí
  const albumTags = page.getByRole("group", { name: "Filtrar el álbum por etiqueta" });
  await albumTags.getByRole("button", { name: /Humor\s*1/ }).click();
  await expect(page.getByRole("button", { name: /^Foto del/ })).toHaveCount(1);
  await expectAccessible(page);

  // Mapa: la foto de Sevilla aparece como una zona; al proveedor solo se le pide el estilo
  await page.context().route("https://teselas.example/**", (route) =>
    route.request().url().endsWith("/estilo.json")
      ? route.fulfill({
          json: {
            version: 8,
            glyphs: "https://teselas.example/fuentes/{fontstack}/{range}.pbf",
            sources: {},
            layers: [{ id: "fondo", type: "background", paint: { "background-color": "#e8e4dc" } }],
          },
        })
      : route.fulfill({ status: 404 }),
  );
  const clusters = page.waitForResponse(
    (r) => /\/map\?/.test(r.url()) && r.url().includes("south=") && r.ok(),
  );
  await page.getByRole("link", { name: "Mapa" }).first().click();
  await expect(page.getByRole("region", { name: "Mapa de las fotos" }).locator("canvas")).toBeVisible();
  const zones = (await (await clusters).json()) as { count: number; bounds: number[] }[];
  expect(zones.map((z) => z.count)).toEqual([1]);
  await page.goto(`/?zona=${zones[0]?.bounds.join(",") ?? ""}`);
  await expect(page.getByRole("button", { name: /^Foto del/ })).toHaveCount(1);
  await expect(page.getByLabel("Solo la zona elegida en el mapa")).toBeChecked();

  // Exportar todos los álbumes, solo con una etiqueta
  await page.goto("/exportar");
  await page.getByLabel("Qué exportar").selectOption("all-albums");
  await page.getByLabel(/Humor/).check();
  await page.getByRole("button", { name: "Preparar la exportación" }).click();
  await expect(page.getByText(/1 elementos/).first()).toBeVisible();
  await page.getByLabel(/Humor/).uncheck();
  await page.getByLabel("Qué exportar").selectOption("space");

  // Exportar el espacio entero y descargarlo
  await expectAccessible(page);
  await page.getByRole("button", { name: "Preparar la exportación" }).click();
  const zipLink = page.getByRole("link", { name: /\.zip$/ }).first();
  await expect(zipLink).toBeVisible({ timeout: 90_000 });
  const [download] = await Promise.all([page.waitForEvent("download"), zipLink.click()]);
  expect(await download.failure()).toBeNull();
  expect(download.suggestedFilename()).toBe("Pareja.zip");

  // PWA instalable: manifiesto e iconos, y el service worker registrado
  const manifest = (await (await page.request.get("/manifest.webmanifest")).json()) as {
    icons: { sizes: string }[];
  };
  expect(manifest.icons.map((i) => i.sizes)).toContain("512x512");
  const registered = await page.evaluate(async () => {
    const ready = navigator.serviceWorker.ready.then(() => true);
    return Promise.race([ready, new Promise((r) => setTimeout(() => r(false), 10_000))]);
  });
  expect(registered).toBe(true);

  // App Android: se descarga con sesión
  const android = (await (await page.request.get("/api/v1/app/android")).json()) as { available: boolean };
  expect(android.available).toBe(true);
  const apk = await page.request.get("/api/v1/app/android/apk");
  expect(apk.headers()["content-type"]).toBe("application/vnd.android.package-archive");

  expect(consoleErrors.filter((e) => /Content Security Policy|Refused/.test(e))).toEqual([]);
});
