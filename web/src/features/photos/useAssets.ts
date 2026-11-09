import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { api, type AssetItem } from "../../api/client";
import { toApiParams, type PhotoFilters } from "./filters";

const PAGE = 300;

/** Elementos del espacio por páginas, con refresco mientras haya alguno «procesando». */
export function useAssets(spaceId: string, filters: PhotoFilters, start?: string) {
  const query = useInfiniteQuery({
    queryKey: ["assets", spaceId, filters, start ?? ""],
    queryFn: ({ pageParam }) =>
      api.assets(
        spaceId,
        toApiParams(filters, {
          limit: String(PAGE),
          ...(pageParam ? { cursor: pageParam } : start ? { start } : {}),
        }),
      ),
    initialPageParam: "",
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    refetchInterval: (q) =>
      q.state.data?.pages.some((p) => p.items.some((i) => i.processing_state === "pending")) ? 4000 : false,
  });
  const items = useMemo<AssetItem[]>(() => query.data?.pages.flatMap((p) => p.items) ?? [], [query.data]);
  return { ...query, items };
}

export function useTimeline(spaceId: string, filters: PhotoFilters) {
  return useQuery({
    queryKey: ["timeline", spaceId, filters],
    queryFn: () => api.timeline(spaceId, toApiParams(filters)),
  });
}
