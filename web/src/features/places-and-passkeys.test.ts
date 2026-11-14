import { describe, expect, it } from "vitest";

import { suggestionKey, suggestionName, suggestionRange } from "./albums/suggestion";
import { clusterFeatures } from "./map/clusters";
import { fromBase64Url, toBase64Url } from "./passkeys/webauthn";
import { countryName, placeLabel } from "./photos/format";
import { parseCoordinates } from "./selection/coordinates";

describe("ubicación", () => {
  it("entiende las coordenadas copiadas de un mapa", () => {
    expect(parseCoordinates("40.4168, -3.7038")).toEqual({ lat: 40.4168, lon: -3.7038 });
    expect(parseCoordinates(" 37.39 -5.99 ")).toEqual({ lat: 37.39, lon: -5.99 });
    expect(parseCoordinates("91, 0")).toBeNull();
    expect(parseCoordinates("Sevilla")).toBeNull();
    expect(parseCoordinates("1, 2, 3")).toBeNull();
  });

  it("nombra el lugar con el país en español", () => {
    expect(countryName("es")).toBe("España");
    expect(countryName("??")).toBe("??");
    expect(placeLabel({ place_name: "Sevilla", place_country: "ES" })).toBe("Sevilla, España");
    expect(placeLabel({})).toBeNull();
  });
});

describe("mapa", () => {
  it("convierte las zonas en GeoJSON con lon/lat", () => {
    const fc = clusterFeatures([{ lat: 40, lon: -3, count: 5, bounds: [39, -4, 41, -2], cover_id: "a" }]);
    expect(fc.features[0]?.geometry.coordinates).toEqual([-3, 40]);
    expect(fc.features[0]?.properties).toEqual({ count: 5, bounds: "39,-4,41,-2", cover: "a" });
  });
});

describe("sugerencias de álbum", () => {
  const s = {
    asset_ids: ["a", "b"],
    count: 12,
    start: "2026-10-03T10:00:00",
    end: "2026-10-07T18:00:00",
    place: "Cádiz",
  };
  it("propone nombre y fechas", () => {
    expect(suggestionName(s)).toBe("Cádiz, octubre de 2026");
    expect(suggestionName({ ...s, place: null })).toBe("Octubre de 2026");
    expect(suggestionRange(s)).toBe("del 3 al 7 de octubre");
    expect(suggestionRange({ ...s, end: "2026-11-02T10:00:00" })).toBe("del 3 de octubre al 2 de noviembre");
    expect(suggestionKey(s)).toBe("2026-10-03T10:00:00|12");
  });
});

describe("llaves de acceso", () => {
  it("convierte base64url en los dos sentidos", () => {
    const bytes = new Uint8Array([0, 251, 255, 62, 63, 1]);
    const text = toBase64Url(bytes.buffer);
    expect(text).not.toMatch(/[+/=]/);
    expect(new Uint8Array(fromBase64Url(text))).toEqual(bytes);
  });
});

describe("filtro por zona del mapa", () => {
  it("pasa los límites a la API y cuenta como filtro", async () => {
    const { activeCount, readFilters, toApiParams } = await import("./photos/filters");
    const f = readFilters(new URLSearchParams("zona=39,-4,41,-2"));
    const p = toApiParams(f);
    expect([p.get("south"), p.get("west"), p.get("north"), p.get("east")]).toEqual(["39", "-4", "41", "-2"]);
    expect(activeCount(f)).toBe(1);
    expect(toApiParams(readFilters(new URLSearchParams("zona=nada"))).has("south")).toBe(false);
  });
});
