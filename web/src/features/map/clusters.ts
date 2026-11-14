import type { MapCluster } from "../../api/client";

export function clusterFeatures(clusters: MapCluster[]) {
  return {
    type: "FeatureCollection" as const,
    features: clusters.map((c) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [c.lon, c.lat] },
      properties: { count: c.count, bounds: c.bounds.join(","), cover: c.cover_id },
    })),
  };
}
