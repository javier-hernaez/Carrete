import { createSHA256 } from "hash-wasm";

const SLICE = 8 * 1024 * 1024;

/** SHA-256 de un fichero leyéndolo por trozos: no carga en memoria un vídeo de varios GB. */
export async function sha256File(file: Blob, onProgress?: (fraction: number) => void): Promise<string> {
  const hasher = await createSHA256();
  hasher.init();
  for (let offset = 0; offset < file.size; offset += SLICE) {
    const chunk = new Uint8Array(await file.slice(offset, offset + SLICE).arrayBuffer());
    hasher.update(chunk);
    onProgress?.(Math.min(1, (offset + chunk.length) / file.size));
  }
  return hasher.digest("hex");
}
