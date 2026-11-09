import { describe, expect, it } from "vitest";

import { filesFromDataTransfer, filesFromInput } from "./folders";
import { isMedia } from "./queue";

function fileEntry(path: string, file: File): FileSystemFileEntry {
  return {
    isFile: true,
    isDirectory: false,
    fullPath: path,
    file: (ok: (f: File) => void) => ok(file),
  } as unknown as FileSystemFileEntry;
}

function dirEntry(path: string, children: FileSystemEntry[]): FileSystemDirectoryEntry {
  let served = false;
  return {
    isFile: false,
    isDirectory: true,
    fullPath: path,
    createReader: () => ({
      readEntries: (ok: (e: FileSystemEntry[]) => void) => {
        ok(served ? [] : children);
        served = true;
      },
    }),
  } as unknown as FileSystemDirectoryEntry;
}

describe("carpetas", () => {
  it("recorre carpetas soltadas conservando la ruta", async () => {
    const a = new File(["a"], "a.jpg", { type: "image/jpeg" });
    const b = new File(["b"], "b.mp4", { type: "video/mp4" });
    const tree = dirEntry("/Asturias 2025", [
      fileEntry("/Asturias 2025/a.jpg", a),
      dirEntry("/Asturias 2025/día 2", [fileEntry("/Asturias 2025/día 2/b.mp4", b)]),
    ]);
    const loose = fileEntry("/suelta.jpg", a);
    const dt = {
      items: [{ webkitGetAsEntry: () => tree }, { webkitGetAsEntry: () => loose }],
      files: [],
    } as unknown as DataTransfer;
    const out = await filesFromDataTransfer(dt);
    expect(out.map((f) => f.relativePath)).toEqual([
      "Asturias 2025/a.jpg",
      "Asturias 2025/día 2/b.mp4",
      null,
    ]);
  });

  it("sin soporte de carpetas usa la lista de ficheros", async () => {
    const a = new File(["a"], "a.jpg");
    const dt = { items: [{}], files: [a] } as unknown as DataTransfer;
    expect(await filesFromDataTransfer(dt)).toEqual([{ file: a, relativePath: null }]);
  });

  it("lee el selector de carpeta", () => {
    const a = new File(["a"], "a.jpg");
    Object.defineProperty(a, "webkitRelativePath", { value: "Viaje/a.jpg" });
    const b = new File(["b"], "b.jpg");
    expect(filesFromInput([a, b] as unknown as FileList)).toEqual([
      { file: a, relativePath: "Viaje/a.jpg" },
      { file: b, relativePath: null },
    ]);
    expect(filesFromInput(null)).toEqual([]);
  });

  it("solo acepta fotos y vídeos", () => {
    expect(isMedia(new File([""], "x.heic"))).toBe(true);
    expect(isMedia(new File([""], "x", { type: "video/quicktime" }))).toBe(true);
    expect(isMedia(new File([""], "x.MOV"))).toBe(true);
    expect(isMedia(new File([""], "x.pdf", { type: "application/pdf" }))).toBe(false);
    expect(isMedia(new File([""], "notas.txt"))).toBe(false);
  });
});
