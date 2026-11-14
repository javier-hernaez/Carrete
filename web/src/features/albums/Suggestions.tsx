import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";

import { api, type Suggestion } from "../../api/client";
import { Button } from "../../design-system/components/Button";
import { Card } from "../../design-system/components/Card";
import styles from "./albums.module.css";
import { suggestionKey, suggestionName, suggestionRange } from "./suggestion";

const DISMISSED = "carrete.sugerencias-descartadas";
function readDismissed(): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(DISMISSED) ?? "[]");
    return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

/** Sugerencias de álbum: grupos de fotos de días seguidos que aún no están en ningún álbum. */
export function Suggestions({ spaceId }: { spaceId: string }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [dismissed, setDismissed] = useState(readDismissed);
  const suggestions = useQuery({
    queryKey: ["suggestions", spaceId],
    queryFn: () => api.suggestions(spaceId),
  });
  const create = useMutation({
    mutationFn: (s: Suggestion) => api.createAlbum(spaceId, suggestionName(s), s.asset_ids),
    onSuccess: async (album) => {
      await queryClient.invalidateQueries({ queryKey: ["albums"] });
      await queryClient.invalidateQueries({ queryKey: ["suggestions"] });
      await navigate(`/albumes/${album.id}`);
    },
  });
  const dismiss = (s: Suggestion) => {
    const next = [...dismissed, suggestionKey(s)].slice(-200);
    setDismissed(next);
    try {
      localStorage.setItem(DISMISSED, JSON.stringify(next));
    } catch {
      // Sin almacenamiento local la sugerencia vuelve a salir: no pasa nada.
    }
  };
  const visible = (suggestions.data ?? []).filter((s) => !dismissed.includes(suggestionKey(s))).slice(0, 3);
  if (visible.length === 0) return null;
  return (
    <Card title="Sugerencias">
      <ul className={styles.suggestions}>
        {visible.map((s) => (
          <li key={suggestionKey(s)} className={styles.suggestion}>
            <span className={styles.suggestionText}>
              ¿Crear un álbum con estas {s.count} fotos {suggestionRange(s)}
              {s.place ? ` en ${s.place}` : ""}?
            </span>
            <Button variant="primary" disabled={create.isPending} onClick={() => create.mutate(s)}>
              Crear «{suggestionName(s)}»
            </Button>
            <Button variant="ghost" onClick={() => dismiss(s)}>
              Ahora no
            </Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
