/**
 * Descodificador de ThumbHash (Evan Wallace, licencia MIT, https://evanw.github.io/thumbhash/).
 * Devuelve una imagen diminuta (≤32 px) que el navegador amplía con desenfoque como marcador.
 */

export function thumbHashToApproximateAspectRatio(hash: Uint8Array): number {
  const header = hash[3] ?? 0;
  const hasAlpha = (hash[2] ?? 0) & 0x80;
  const isLandscape = (hash[4] ?? 0) & 0x80;
  const lx = isLandscape ? (hasAlpha ? 5 : 7) : header & 7;
  const ly = isLandscape ? header & 7 : hasAlpha ? 5 : 7;
  return lx / ly;
}

export function thumbHashToRGBA(hash: Uint8Array): {
  w: number;
  h: number;
  rgba: Uint8ClampedArray<ArrayBuffer>;
} {
  const { PI, min, max, cos, round } = Math;
  const at = (i: number) => hash[i] ?? 0;
  const header24 = at(0) | (at(1) << 8) | (at(2) << 16);
  const header16 = at(3) | (at(4) << 8);
  const lDc = (header24 & 63) / 63;
  const pDc = ((header24 >> 6) & 63) / 31.5 - 1;
  const qDc = ((header24 >> 12) & 63) / 31.5 - 1;
  const lScale = ((header24 >> 18) & 31) / 31;
  const hasAlpha = header24 >> 23;
  const pScale = ((header16 >> 3) & 63) / 63;
  const qScale = ((header16 >> 9) & 63) / 63;
  const isLandscape = header16 >> 15;
  const lx = max(3, isLandscape ? (hasAlpha ? 5 : 7) : header16 & 7);
  const ly = max(3, isLandscape ? header16 & 7 : hasAlpha ? 5 : 7);
  const aDc = hasAlpha ? (at(5) & 15) / 15 : 1;
  const aScale = (at(5) >> 4) / 15;
  const acStart = hasAlpha ? 6 : 5;
  let acIndex = 0;
  const decodeChannel = (nx: number, ny: number, scale: number) => {
    const ac: number[] = [];
    for (let cy = 0; cy < ny; cy++)
      for (let cx = cy ? 0 : 1; cx * ny < nx * (ny - cy); cx++) {
        ac.push((((at(acStart + (acIndex >> 1)) >> ((acIndex & 1) << 2)) & 15) / 7.5 - 1) * scale);
        acIndex++;
      }
    return ac;
  };
  const lAc = decodeChannel(lx, ly, lScale);
  const pAc = decodeChannel(3, 3, pScale * 1.25);
  const qAc = decodeChannel(3, 3, qScale * 1.25);
  const aAc = hasAlpha ? decodeChannel(5, 5, aScale) : [];
  const ratio = thumbHashToApproximateAspectRatio(hash);
  const w = round(ratio > 1 ? 32 : 32 * ratio);
  const h = round(ratio > 1 ? 32 / ratio : 32);
  const rgba = new Uint8ClampedArray(new ArrayBuffer(w * h * 4));
  const fx: number[] = [];
  const fy: number[] = [];
  for (let y = 0, i = 0; y < h; y++) {
    for (let x = 0; x < w; x++, i += 4) {
      let l = lDc;
      let p = pDc;
      let q = qDc;
      let a = aDc;
      for (let cx = 0, n = max(lx, hasAlpha ? 5 : 3); cx < n; cx++) fx[cx] = cos((PI / w) * (x + 0.5) * cx);
      for (let cy = 0, n = max(ly, hasAlpha ? 5 : 3); cy < n; cy++) fy[cy] = cos((PI / h) * (y + 0.5) * cy);
      for (let cy = 0, j = 0; cy < ly; cy++)
        for (let cx = cy ? 0 : 1, fy2 = (fy[cy] ?? 0) * 2; cx * ly < lx * (ly - cy); cx++, j++)
          l += (lAc[j] ?? 0) * (fx[cx] ?? 0) * fy2;
      for (let cy = 0, j = 0; cy < 3; cy++)
        for (let cx = cy ? 0 : 1, fy2 = (fy[cy] ?? 0) * 2; cx < 3 - cy; cx++, j++) {
          const f = (fx[cx] ?? 0) * fy2;
          p += (pAc[j] ?? 0) * f;
          q += (qAc[j] ?? 0) * f;
        }
      if (hasAlpha)
        for (let cy = 0, j = 0; cy < 5; cy++)
          for (let cx = cy ? 0 : 1, fy2 = (fy[cy] ?? 0) * 2; cx < 5 - cy; cx++, j++)
            a += (aAc[j] ?? 0) * (fx[cx] ?? 0) * fy2;
      const b = l - (2 / 3) * p;
      const r = (3 * l - b + q) / 2;
      const g = r - q;
      rgba[i] = max(0, 255 * min(1, r));
      rgba[i + 1] = max(0, 255 * min(1, g));
      rgba[i + 2] = max(0, 255 * min(1, b));
      rgba[i + 3] = max(0, 255 * min(1, a));
    }
  }
  return { w, h, rgba };
}

export function decodeBase64(value: string): Uint8Array {
  const binary = atob(value);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

/** Color medio (para fondos) y una imagen data: diminuta, o null si el navegador no tiene canvas. */
export function thumbHashToPlaceholder(b64: string | null | undefined): {
  color: string;
  url: string | null;
} {
  if (!b64) return { color: "var(--color-surface-2)", url: null };
  try {
    const { w, h, rgba } = thumbHashToRGBA(decodeBase64(b64));
    let r = 0;
    let g = 0;
    let b = 0;
    for (let i = 0; i < rgba.length; i += 4) {
      r += rgba[i] ?? 0;
      g += rgba[i + 1] ?? 0;
      b += rgba[i + 2] ?? 0;
    }
    const n = rgba.length / 4;
    const color = `rgb(${Math.round(r / n)} ${Math.round(g / n)} ${Math.round(b / n)})`;
    const canvas = document.createElement("canvas");
    const ctx = typeof canvas.getContext === "function" ? canvas.getContext("2d") : null;
    if (!ctx) return { color, url: null };
    canvas.width = w;
    canvas.height = h;
    ctx.putImageData(new ImageData(rgba, w, h), 0, 0);
    return { color, url: canvas.toDataURL() };
  } catch {
    return { color: "var(--color-surface-2)", url: null };
  }
}
