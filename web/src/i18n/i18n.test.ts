import { describe, expect, it } from "vitest";

import { t } from ".";

describe("t", () => {
  it("devuelve el texto de la clave", () => {
    expect(t("nav.photos")).toBe("Fotos");
  });

  it("sustituye variables y deja intactas las que faltan", () => {
    expect(t("more.version", { version: "1.0" })).toBe("Versión 1.0");
    expect(t("more.version", {})).toBe("Versión {version}");
  });
});
