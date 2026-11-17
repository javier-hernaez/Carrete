import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";

/** Las que se ofrecen para empezar mientras el espacio no tiene ninguna con ese nombre. */
export const STARTER_TAGS = ["Personas", "Paisajes", "Humor"];

/** Etiquetas del espacio; con un álbum, solo las que hay dentro y su recuento allí. */
export function useTags(spaceId: string, albumId?: string) {
  return useQuery({
    queryKey: ["tags", spaceId, albumId ?? ""],
    queryFn: () => api.tags(spaceId, albumId),
    enabled: !!spaceId,
    staleTime: 30_000,
  });
}

/** Cuántos de los elementos tienen la etiqueta: todos, algunos o ninguno. */
export function coverage(
  tagId: string,
  ids: readonly string[],
  tagsOf: (id: string) => readonly string[],
): "all" | "some" | "none" {
  let with_ = 0;
  for (const id of ids) if (tagsOf(id).includes(tagId)) with_++;
  return with_ === 0 ? "none" : with_ === ids.length ? "all" : "some";
}
