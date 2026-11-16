import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";

import { api } from "../../api/client";
import { errorMessage } from "../../app/errors";
import { showToast } from "../toast/toast";

type Message = (n: number) => string;

const plural =
  (one: string, many: (n: number) => string): Message =>
  (n) =>
    n === 1 ? one : many(n);

/**
 * Acciones sobre elementos con aviso y «Deshacer». El servidor devuelve la operación inversa
 * exacta (instantánea por elemento), así que deshacer devuelve cada foto a su estado anterior.
 */
export function useAssetActions(spaceId: string) {
  const queryClient = useQueryClient();
  const refresh = useCallback(async () => {
    await Promise.all(
      ["assets", "timeline", "trash", "albums", "album", "tags", "counters", "duplicates", "asset"].map(
        (key) => queryClient.invalidateQueries({ queryKey: [key] }),
      ),
    );
  }, [queryClient]);

  const run = useCallback(
    async (
      ids: string[],
      action: string,
      extra: Record<string, unknown>,
      message: Message,
      options: { quiet?: boolean; zero?: string } = {},
    ) => {
      try {
        const result = await api.batch(spaceId, ids, action, extra);
        // La lista se recarga en segundo plano: el aviso sale en cuanto el servidor confirma, aunque la
        // conexión sea lenta (antes esperaba a recargarlo todo y parecía que el botón no hacía nada).
        void refresh();
        if (result.count === 0) {
          showToast(options.zero ?? "No ha cambiado nada: ya estaba así");
          return result;
        }
        const undo = result.undo;
        if (!options.quiet || undo) {
          showToast(message(result.count), {
            action: undo
              ? {
                  label: "Deshacer",
                  run: () => {
                    const { action: undoAction, ...rest } = undo as { action: string } & Record<
                      string,
                      unknown
                    >;
                    return api
                      .batch(spaceId, ids, undoAction, rest)
                      .then(refresh)
                      .catch((e: unknown) => showToast(errorMessage(e), { tone: "danger" }));
                  },
                }
              : undefined,
          });
        }
        return result;
      } catch (error) {
        showToast(errorMessage(error), { tone: "danger" });
        return null;
      }
    },
    [spaceId, refresh],
  );

  return useMemo(
    () => ({
      refresh,
      run,
      trash: (ids: string[]) =>
        run(
          ids,
          "trash",
          {},
          plural("Enviada a la papelera", (n) => `${n} enviadas a la papelera`),
        ),
      restore: (ids: string[]) =>
        run(
          ids,
          "restore",
          {},
          plural("Recuperada", (n) => `${n} recuperadas`),
        ),
      review: (ids: string[], state: "kept" | "discarded" | "pending") =>
        run(
          ids,
          "review",
          { state },
          state === "kept"
            ? plural("Marcada como «vale»", (n) => `${n} marcadas como «vale»`)
            : state === "discarded"
              ? plural("Descartada", (n) => `${n} descartadas`)
              : plural("Vuelve a «sin revisar»", (n) => `${n} vuelven a «sin revisar»`),
        ),
      favorite: (ids: string[], value: boolean) =>
        run(
          ids,
          "favorite",
          { value },
          value
            ? plural("Añadida a favoritas", (n) => `${n} añadidas a favoritas`)
            : plural("Quitada de favoritas", (n) => `${n} quitadas de favoritas`),
        ),
      addToAlbum: (ids: string[], albumId: string, albumName: string) =>
        run(
          ids,
          "add_album",
          { album_id: albumId },
          plural(`Añadida a «${albumName}»`, (n) => `${n} añadidas a «${albumName}»`),
          { zero: ids.length === 1 ? `Ya estaba en «${albumName}»` : `Ya estaban en «${albumName}»` },
        ),
      addTag: (ids: string[], tag: { id: string; name: string }) =>
        run(
          ids,
          "add_tag",
          { tag_id: tag.id },
          plural(`Etiqueta «${tag.name}» puesta`, (n) => `«${tag.name}» puesta a ${n}`),
          { zero: `Ya tenían «${tag.name}»` },
        ),
      removeTag: (ids: string[], tag: { id: string; name: string }) =>
        run(
          ids,
          "remove_tag",
          { tag_id: tag.id },
          plural(`Etiqueta «${tag.name}» quitada`, (n) => `«${tag.name}» quitada a ${n}`),
          { zero: `No tenían «${tag.name}»` },
        ),
      removeFromAlbum: (ids: string[], albumId: string) =>
        run(
          ids,
          "remove_album",
          { album_id: albumId },
          plural("Quitada del álbum", (n) => `${n} quitadas del álbum`),
        ),
      setDate: (ids: string[], takenAt: string) =>
        run(
          ids,
          "set_date",
          { taken_at: takenAt },
          plural("Fecha cambiada", (n) => `Fecha cambiada en ${n}`),
        ),
      shiftDate: (ids: string[], minutes: number) =>
        run(
          ids,
          "shift_date",
          { minutes },
          plural("Fecha movida", (n) => `Fecha movida en ${n}`),
        ),
      setLocation: (ids: string[], coords: { lat: number; lon: number } | null) =>
        run(
          ids,
          "set_location",
          coords ?? {},
          coords
            ? plural("Ubicación puesta", (n) => `Ubicación puesta en ${n}`)
            : plural("Ubicación quitada", (n) => `Ubicación quitada en ${n}`),
        ),
    }),
    [refresh, run],
  );
}
