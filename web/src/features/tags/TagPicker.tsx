import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { api, type Tag } from "../../api/client";
import { errorMessage } from "../../app/errors";
import { Button } from "../../design-system/components/Button";
import { Dialog } from "../../design-system/components/Dialog";
import { TextField } from "../../design-system/components/Field";
import { cx } from "../../design-system/cx";
import { useAssetActions } from "../photos/actions";
import { showToast } from "../toast/toast";
import { coverage, STARTER_TAGS, useTags } from "./tags";
import styles from "./tags.module.css";

/**
 * Poner y quitar etiquetas a uno o varios elementos. Cada etiqueta es un interruptor: si todos la
 * tienen, se quita; si no, se pone a todos. Se puede crear una nueva desde aquí.
 */
export function TagPicker({
  spaceId,
  ids,
  tagsOf,
  onClose,
  onChanged,
}: {
  spaceId: string;
  ids: string[];
  tagsOf: (id: string) => readonly string[];
  onClose: () => void;
  /** Aviso de cada cambio (Revisar lo usa para reflejarlo sin recargar su lista). */
  onChanged?: (tag: Tag, has: boolean) => void;
}) {
  const tags = useTags(spaceId);
  const actions = useAssetActions(spaceId);
  const queryClient = useQueryClient();
  // Lo que se ha cambiado aquí manda sobre lo que trae la lista, que se recarga en segundo plano.
  const [changed, setChanged] = useState<Record<string, "all" | "none">>({});
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const state = (tag: Tag) => changed[tag.id] ?? coverage(tag.id, ids, tagsOf);

  const toggle = async (tag: Tag) => {
    const has = state(tag) === "all";
    setChanged((c) => ({ ...c, [tag.id]: has ? "none" : "all" }));
    const result = has ? await actions.removeTag(ids, tag) : await actions.addTag(ids, tag);
    if (!result) setChanged((c) => Object.fromEntries(Object.entries(c).filter(([id]) => id !== tag.id)));
    else onChanged?.(tag, !has);
  };

  const create = async (raw: string) => {
    const clean = raw.trim();
    if (!clean || busy) return;
    setBusy(true);
    setError(null);
    try {
      const tag = await api.createTag(spaceId, clean, ids);
      setChanged((c) => ({ ...c, [tag.id]: "all" }));
      onChanged?.(tag, true);
      setName("");
      showToast(ids.length === 1 ? `Etiqueta «${tag.name}» puesta` : `«${tag.name}» puesta a ${ids.length}`);
      await Promise.all(
        ["tags", "assets", "asset"].map((key) => queryClient.invalidateQueries({ queryKey: [key] })),
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const list = tags.data ?? [];
  const known = new Set(list.map((t) => t.name.toLocaleLowerCase("es")));
  const starters = STARTER_TAGS.filter((n) => !known.has(n.toLocaleLowerCase("es")));
  return (
    <Dialog title={ids.length === 1 ? "Etiquetas" : `Etiquetas de ${ids.length}`} onClose={onClose}>
      {list.length > 0 && (
        <ul className={styles.pickList} aria-label="Etiquetas del espacio">
          {list.map((tag) => {
            const s = state(tag);
            return (
              <li key={tag.id}>
                <button
                  type="button"
                  className={cx(styles.pick, s === "all" && styles.pickOn, s === "some" && styles.pickSome)}
                  aria-pressed={s === "all" ? true : s === "some" ? "mixed" : false}
                  onClick={() => void toggle(tag)}
                >
                  <span className={styles.pickMark} aria-hidden="true">
                    {s === "all" ? "✓" : s === "some" ? "–" : ""}
                  </span>
                  {tag.name}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {starters.length > 0 && (
        <div className={styles.starters}>
          <p className={styles.muted}>{list.length === 0 ? "Para empezar:" : "Sugerencias:"}</p>
          <div className={styles.pickList}>
            {starters.map((n) => (
              <button key={n} type="button" className={styles.pick} onClick={() => void create(n)}>
                + {n}
              </button>
            ))}
          </div>
        </div>
      )}
      <form
        className={styles.newTag}
        onSubmit={(e) => {
          e.preventDefault();
          void create(name);
        }}
      >
        <TextField
          label="Nueva etiqueta"
          placeholder="Comida, Mascotas…"
          value={name}
          maxLength={40}
          onChange={(e) => setName(e.target.value)}
          error={error ?? undefined}
        />
        <Button type="submit" variant="primary" disabled={!name.trim() || busy}>
          Crear y poner
        </Button>
      </form>
      <p className={styles.manage}>
        <Link to="/etiquetas" onClick={onClose}>
          Renombrar o eliminar etiquetas
        </Link>
      </p>
    </Dialog>
  );
}
