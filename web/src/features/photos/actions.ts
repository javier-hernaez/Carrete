import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { api } from "../../api/client";
import { errorMessage } from "../../app/errors";
import { showToast } from "../toast/toast";

/** Acciones sobre elementos con aviso y «Deshacer». */
export function useAssetActions(spaceId: string) {
  const queryClient = useQueryClient();
  const refresh = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["assets", spaceId] }),
      queryClient.invalidateQueries({ queryKey: ["timeline", spaceId] }),
      queryClient.invalidateQueries({ queryKey: ["trash", spaceId] }),
      queryClient.invalidateQueries({ queryKey: ["albums", spaceId] }),
    ]);
  }, [queryClient, spaceId]);

  const run = useCallback(
    async (
      ids: string[],
      action: string,
      extra: Record<string, unknown>,
      message: (n: number) => string,
      undo?: { action: string; extra?: Record<string, unknown> },
    ) => {
      try {
        const { count } = await api.batch(spaceId, ids, action, extra);
        await refresh();
        showToast(message(count), {
          action: undo
            ? {
                label: "Deshacer",
                run: () =>
                  api
                    .batch(spaceId, ids, undo.action, undo.extra ?? {})
                    .then(refresh)
                    .catch((e: unknown) => showToast(errorMessage(e), { tone: "danger" })),
              }
            : undefined,
        });
        return count;
      } catch (error) {
        showToast(errorMessage(error), { tone: "danger" });
        return 0;
      }
    },
    [spaceId, refresh],
  );

  return {
    refresh,
    run,
    trash: (ids: string[]) =>
      run(ids, "trash", {}, (n) => (n === 1 ? "Enviada a la papelera" : `${n} enviadas a la papelera`), {
        action: "restore",
      }),
    restore: (ids: string[]) =>
      run(ids, "restore", {}, (n) => (n === 1 ? "Recuperada" : `${n} recuperadas`), { action: "trash" }),
  };
}
