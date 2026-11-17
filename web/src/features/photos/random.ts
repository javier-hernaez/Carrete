import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";

/** Una foto al azar de todo el espacio (esté o no en un álbum). Cambia al pulsar «Otra». */
export function useRandomPick(spaceId: string) {
  return useQuery({
    queryKey: ["random", spaceId],
    queryFn: () => api.randomAsset(spaceId, new URLSearchParams({ kind: "photo" })),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}
