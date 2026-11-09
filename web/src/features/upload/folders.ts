/** Lee lo soltado al arrastrar, incluidas carpetas enteras, con su ruta relativa. */
export async function filesFromDataTransfer(
  dt: DataTransfer,
): Promise<{ file: File; relativePath: string | null }[]> {
  const entries = Array.from(dt.items)
    .map((item) => (typeof item.webkitGetAsEntry === "function" ? item.webkitGetAsEntry() : null))
    .filter((e): e is FileSystemEntry => e !== null);
  if (entries.length === 0) return Array.from(dt.files).map((file) => ({ file, relativePath: null }));
  const out: { file: File; relativePath: string | null }[] = [];
  for (const entry of entries) await walk(entry, out);
  return out;
}

async function walk(
  entry: FileSystemEntry,
  out: { file: File; relativePath: string | null }[],
): Promise<void> {
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) => {
      (entry as FileSystemFileEntry).file(resolve, reject);
    });
    const path = entry.fullPath.replace(/^\//, "");
    out.push({ file, relativePath: path.includes("/") ? path : null });
    return;
  }
  if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    // readEntries devuelve los hijos por tandas: hay que llamar hasta que no queden.
    for (;;) {
      const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => {
        reader.readEntries(resolve, reject);
      });
      if (batch.length === 0) break;
      for (const child of batch) await walk(child, out);
    }
  }
}

export function filesFromInput(list: FileList | null): { file: File; relativePath: string | null }[] {
  return Array.from(list ?? []).map((file) => ({
    file,
    relativePath:
      file.webkitRelativePath && file.webkitRelativePath.includes("/") ? file.webkitRelativePath : null,
  }));
}
