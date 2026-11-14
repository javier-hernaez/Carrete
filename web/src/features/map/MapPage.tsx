import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { api } from "../../api/client";
import { useSession } from "../../app/session";
import { Alert, PageTitle } from "../../design-system/components/Card";
import { EmptyState } from "../../design-system/components/EmptyState";
import { t } from "../../i18n";
import { clusterFeatures } from "./clusters";
import styles from "./map.module.css";

type MapLibre = typeof import("maplibre-gl");
type MapInstance = InstanceType<MapLibre["Map"]>;

/**
 * Mapa del espacio: fotos con GPS agrupadas por zonas. MapLibre se carga solo al abrir esta
 * pantalla. Al proveedor de teselas solo se le piden las zonas que se miran: nunca fotos ni coordenadas.
 */
export function MapPage() {
  const { space } = useSession();
  const info = useQuery({ queryKey: ["info"], queryFn: api.info, staleTime: Infinity });
  if (!space) return null;
  const styleUrl = info.data?.map_style_url;
  return (
    <div>
      <PageTitle>{t("nav.map")}</PageTitle>
      {info.data && !styleUrl && (
        <EmptyState title="El mapa no está activado">
          El administrador puede activarlo con CARRETE_MAP_STYLE_URL.
        </EmptyState>
      )}
      {styleUrl && <SpaceMap spaceId={space.id} styleUrl={styleUrl} />}
    </div>
  );
}

function SpaceMap({ spaceId, styleUrl }: { spaceId: string; styleUrl: string }) {
  const container = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [empty, setEmpty] = useState(false);

  useEffect(() => {
    let map: MapInstance | null = null;
    let cancelled = false;
    void import("maplibre-gl")
      .then(async (maplibre: MapLibre) => {
        await import("maplibre-gl/dist/maplibre-gl.css");
        if (cancelled || !container.current) return;
        const centre = (params.get("centro") ?? "").split(",").map(Number);
        const hasCentre = centre.length === 2 && centre.every((n) => Number.isFinite(n));
        map = new maplibre.Map({
          container: container.current,
          style: styleUrl,
          center: hasCentre ? [centre[1] ?? 0, centre[0] ?? 0] : [-3.7, 40.2],
          zoom: hasCentre ? 12 : 4,
          attributionControl: { compact: true },
        });
        map.addControl(new maplibre.NavigationControl({ showCompass: false }), "top-right");
        const current = map;
        const refresh = async () => {
          const b = current.getBounds();
          const clusters = await api.mapClusters(spaceId, {
            zoom: String(Math.round(current.getZoom())),
            south: String(Math.max(-90, b.getSouth())),
            west: String(Math.max(-180, b.getWest())),
            north: String(Math.min(90, b.getNorth())),
            east: String(Math.min(180, b.getEast())),
          });
          const source = current.getSource("fotos") as { setData?: (d: unknown) => void } | undefined;
          source?.setData?.(clusterFeatures(clusters));
        };
        current.on("load", () => {
          current.addSource("fotos", { type: "geojson", data: clusterFeatures([]) });
          current.addLayer({
            id: "zonas",
            type: "circle",
            source: "fotos",
            paint: {
              "circle-color": "#a84b15",
              "circle-opacity": 0.85,
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 2,
              "circle-radius": ["interpolate", ["linear"], ["get", "count"], 1, 10, 50, 20, 1000, 34],
            },
          });
          current.addLayer({
            id: "numeros",
            type: "symbol",
            source: "fotos",
            layout: {
              "text-field": ["to-string", ["get", "count"]],
              "text-size": 12,
              "text-allow-overlap": true,
            },
            paint: { "text-color": "#ffffff" },
          });
          current.on("click", "zonas", (event) => {
            const feature = event.features?.[0];
            const bounds = feature?.properties.bounds as string | undefined;
            if (bounds) void navigate(`/?zona=${encodeURIComponent(bounds)}`);
          });
          current.on("mouseenter", "zonas", () => (current.getCanvas().style.cursor = "pointer"));
          current.on("mouseleave", "zonas", () => (current.getCanvas().style.cursor = ""));
          current.on("moveend", () => void refresh().catch(() => undefined));
          void api
            .mapClusters(spaceId, { zoom: "1" })
            .then((all) => {
              setEmpty(all.length === 0);
              if (!hasCentre && all.length > 0) {
                const lats = all.flatMap((c) => [c.bounds[0] ?? 0, c.bounds[2] ?? 0]);
                const lons = all.flatMap((c) => [c.bounds[1] ?? 0, c.bounds[3] ?? 0]);
                current.fitBounds(
                  [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)],
                  { padding: 60, maxZoom: 12 },
                );
              }
              return refresh();
            })
            .catch(() => undefined);
        });
      })
      .catch(() => setError("No se pudo cargar el mapa en este navegador."));
    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [spaceId, styleUrl, navigate, params]);

  return (
    <div className={styles.wrap}>
      {error && <Alert tone="danger">{error}</Alert>}
      {empty && <Alert>{t("map.empty.text")}</Alert>}
      <div ref={container} className={styles.map} role="region" aria-label="Mapa de las fotos" />
      <p className={styles.note}>
        Las fotos de WhatsApp no traen ubicación, y Android la quita al compartir salvo si se suben con la app
        de Carrete. Para ponerla a mano, selecciona las fotos y pulsa «Lugar…».
      </p>
    </div>
  );
}
