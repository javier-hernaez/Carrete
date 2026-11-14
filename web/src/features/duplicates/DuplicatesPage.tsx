import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type DuplicateGroup } from "../../api/client";
import { errorMessage } from "../../app/errors";
import { canEdit, useSession } from "../../app/session";
import { Button } from "../../design-system/components/Button";
import { PageTitle } from "../../design-system/components/Card";
import { Dialog } from "../../design-system/components/Dialog";
import { EmptyState } from "../../design-system/components/EmptyState";
import { cx } from "../../design-system/cx";
import { formatBytes, formatDateTime, SOURCE_LABEL } from "../photos/format";
import { showToast } from "../toast/toast";
import styles from "./duplicates.module.css";

/** Repetidas y parecidas. */
export function DuplicatesPage() {
  const { space } = useSession();
  const queryClient = useQueryClient();
  const spaceId = space?.id ?? "";
  const groups = useQuery({
    queryKey: ["duplicates", spaceId],
    queryFn: () => api.duplicates(spaceId),
    enabled: !!space,
  });
  const [preview, setPreview] = useState<{ groups: number; trash: number } | null>(null);
  const refresh = () =>
    Promise.all(
      ["duplicates", "assets", "counters", "timeline"].map((k) =>
        queryClient.invalidateQueries({ queryKey: [k] }),
      ),
    );
  if (!space) return null;
  const editor = canEdit(space);

  const applyObvious = async () => {
    setPreview(null);
    try {
      const result = await api.resolveObvious(spaceId, true);
      await refresh();
      showToast(`${result.groups} grupos resueltos; ${result.trashed.length} a la papelera`, {
        action: {
          label: "Deshacer",
          run: async () => {
            await api.batch(spaceId, result.trashed, "restore");
            await Promise.all(result.group_ids.map((g) => api.reopenDuplicates(spaceId, g)));
            await refresh();
          },
        },
      });
    } catch (e) {
      showToast(errorMessage(e), { tone: "danger" });
    }
  };

  return (
    <div>
      <PageTitle
        actions={
          editor && (groups.data?.length ?? 0) > 1 ? (
            <Button
              onClick={() =>
                void api
                  .resolveObvious(spaceId, false)
                  .then(setPreview)
                  .catch((e: unknown) => showToast(errorMessage(e), { tone: "danger" }))
              }
            >
              Resolver los evidentes
            </Button>
          ) : undefined
        }
      >
        Repetidas
      </PageTitle>
      {groups.isSuccess && groups.data.length === 0 && (
        <EmptyState title="No hay repetidas">
          Cuando subas la misma foto en otra calidad o ráfagas parecidas, aparecerán aquí para elegir.
        </EmptyState>
      )}
      <ul className={styles.groups} aria-label="Grupos de repetidas">
        {groups.data?.map((group) => (
          <Group key={group.id} spaceId={spaceId} group={group} editor={editor} onDone={refresh} />
        ))}
      </ul>
      {preview && (
        <Dialog title="Resolver los grupos evidentes" onClose={() => setPreview(null)}>
          {preview.groups === 0 ? (
            <p>No hay grupos evidentes: revisa los demás uno a uno.</p>
          ) : (
            <>
              <p>
                Hay {preview.groups} grupos casi idénticos con una mejor clara. Se conserva la mejor de cada
                uno y {preview.trash} van a la papelera (se pueden recuperar).
              </p>
              <Button variant="primary" onClick={() => void applyObvious()}>
                Resolver {preview.groups} grupos
              </Button>
            </>
          )}
        </Dialog>
      )}
    </div>
  );
}

function Group({
  spaceId,
  group,
  editor,
  onDone,
}: {
  spaceId: string;
  group: DuplicateGroup;
  editor: boolean;
  onDone: () => Promise<unknown>;
}) {
  const best = group.members.find((m) => m.best)?.id ?? group.members[0]?.id ?? "";
  const [keep, setKeep] = useState<ReadonlySet<string>>(new Set([best]));
  const toggle = (id: string) =>
    setKeep((k) => {
      const next = new Set(k);
      if (next.has(id) && next.size > 1) next.delete(id);
      else next.add(id);
      return next;
    });
  const resolve = async (ids: string[]) => {
    try {
      const { trashed } = await api.resolveDuplicates(spaceId, group.id, ids);
      await onDone();
      showToast(trashed.length === 1 ? "Una a la papelera" : `${trashed.length} a la papelera`, {
        action: {
          label: "Deshacer",
          run: async () => {
            await api.batch(spaceId, trashed, "restore");
            await api.reopenDuplicates(spaceId, group.id);
            await onDone();
          },
        },
      });
    } catch (e) {
      showToast(errorMessage(e), { tone: "danger" });
    }
  };
  return (
    <li className={styles.group}>
      <div className={styles.members}>
        {group.members.map((m) => (
          <figure key={m.id} className={cx(styles.member, keep.has(m.id) && styles.kept)}>
            <button
              type="button"
              className={styles.pick}
              aria-pressed={keep.has(m.id)}
              onClick={() => toggle(m.id)}
              disabled={!editor}
            >
              {m.processing_state === "ready" && (
                <img src={`/api/v1/assets/${m.id}/preview`} alt="" loading="lazy" />
              )}
              {m.best && <span className={styles.best}>Mejor</span>}{" "}
              <span className={styles.mark}>{keep.has(m.id) ? "Se queda" : "Papelera"}</span>
              <span className="visually-hidden">: {m.original_filename}</span>
            </button>
            <figcaption className={styles.caption}>
              <strong>{m.width && m.height ? `${m.width}×${m.height}` : "—"}</strong> ·{" "}
              {formatBytes(m.size_bytes)}
              <br />
              {SOURCE_LABEL[m.source]}
              {m.has_exif_date && " · con EXIF"}
              <br />
              {formatDateTime(m.taken_at, m.taken_at_offset)}
            </figcaption>
          </figure>
        ))}
      </div>
      {editor && (
        <div className={styles.actions}>
          <Button variant="primary" onClick={() => void resolve([best])}>
            Quedarme con la mejor
          </Button>
          {(keep.size > 1 || !keep.has(best)) && (
            <Button onClick={() => void resolve([...keep])}>Quedarme con las marcadas</Button>
          )}
          <Button
            variant="ghost"
            onClick={() =>
              void api
                .dismissDuplicates(spaceId, group.id)
                .then(onDone)
                .then(() => showToast("No se volverán a proponer"))
            }
          >
            No son repetidas
          </Button>
        </div>
      )}
    </li>
  );
}
