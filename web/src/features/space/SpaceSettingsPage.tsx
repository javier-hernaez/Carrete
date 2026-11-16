import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type Role } from "../../api/client";
import { errorMessage } from "../../app/errors";
import { RoleHelp, RoleSummary } from "../../app/RoleHelp";
import { ROLE_OPTIONS } from "../../app/roles";
import { isOwner, useSession } from "../../app/session";
import { Button } from "../../design-system/components/Button";
import { Alert, Card, PageTitle } from "../../design-system/components/Card";
import { SelectField, TextField } from "../../design-system/components/Field";
import styles from "../page.module.css";

export function SpaceSettingsPage() {
  const { space } = useSession();
  if (!space) return <NewSpaceCard />;
  return (
    <div className={styles.narrow}>
      <PageTitle>Espacio «{space.name}»</PageTitle>
      {isOwner(space) && <SpaceNameCard />}
      <MembersCard />
      {isOwner(space) && <InviteCard />}
      <NewSpaceCard />
    </div>
  );
}

function SpaceNameCard() {
  const { space, refresh } = useSession();
  const [name, setName] = useState(space?.name ?? "");
  const update = useMutation({
    mutationFn: (body: { name?: string; archived?: boolean }) => api.updateSpace(space?.id ?? "", body),
    onSuccess: refresh,
  });
  if (!space) return null;
  return (
    <Card title="Nombre">
      <form
        className={styles.inline}
        onSubmit={(e) => {
          e.preventDefault();
          update.mutate({ name });
        }}
      >
        <TextField
          label="Nombre del espacio"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className={styles.grow}
        />
        <Button type="submit" disabled={update.isPending || name === space.name}>
          Guardar
        </Button>
      </form>
      <Button variant="ghost" onClick={() => update.mutate({ archived: !space.archived })}>
        {space.archived ? "Desarchivar espacio" : "Archivar espacio"}
      </Button>
      {update.isError && <Alert tone="danger">{errorMessage(update.error)}</Alert>}
    </Card>
  );
}

function MembersCard() {
  const { space, refresh } = useSession();
  const queryClient = useQueryClient();
  const spaceId = space?.id ?? "";
  const members = useQuery({
    queryKey: ["members", spaceId],
    queryFn: () => api.members(spaceId),
    enabled: !!space,
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["members", spaceId] });
  const role = useMutation({
    mutationFn: ({ user, value }: { user: string; value: Role }) => api.changeRole(spaceId, user, value),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: (user: string) => api.removeMember(spaceId, user),
    onSuccess: async (_, user) => {
      await invalidate();
      if (members.data?.find((m) => m.user_id === user)?.is_you) await refresh();
    },
  });
  const owner = isOwner(space);
  const error = role.error ?? remove.error;
  return (
    <Card title="Miembros">
      {error && <Alert tone="danger">{errorMessage(error)}</Alert>}
      <ul className={styles.list}>
        {members.data?.map((m) => (
          <li key={m.user_id} className={styles.row}>
            <div className={styles.grow}>
              <strong>{m.display_name}</strong>
              {m.is_you && <span className={styles.badge}>Tú</span>}
              <div className={styles.muted}>@{m.username}</div>
            </div>
            {owner ? (
              <SelectField
                label={`Rol de ${m.display_name}`}
                hideLabel
                value={m.role}
                options={ROLE_OPTIONS}
                onChange={(e) => role.mutate({ user: m.user_id, value: e.target.value as Role })}
              />
            ) : (
              <span className={styles.muted}>{ROLE_OPTIONS.find((o) => o.value === m.role)?.label}</span>
            )}
            {(owner || m.is_you) && (
              <Button variant="ghost" onClick={() => remove.mutate(m.user_id)}>
                {m.is_you ? "Salir" : "Quitar"}
              </Button>
            )}
          </li>
        ))}
      </ul>
      <RoleHelp />
    </Card>
  );
}

function InviteCard() {
  const { space } = useSession();
  const queryClient = useQueryClient();
  const spaceId = space?.id ?? "";
  const [role, setRole] = useState<Role>("collaborator");
  const pending = useQuery({ queryKey: ["invitations", spaceId], queryFn: () => api.invitations(spaceId) });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["invitations", spaceId] });
  const create = useMutation({ mutationFn: () => api.invite(spaceId, role), onSuccess: invalidate });
  const revoke = useMutation({ mutationFn: api.revokeInvitation, onSuccess: invalidate });
  const format = new Intl.DateTimeFormat("es", { dateStyle: "medium" });
  return (
    <Card title="Invitar">
      <p className={styles.muted}>
        Crea un enlace de un solo uso y envíaselo por WhatsApp. Caduca a los 7 días.
      </p>
      <div className={styles.inline}>
        <SelectField
          label="Rol"
          value={role}
          options={ROLE_OPTIONS}
          onChange={(e) => setRole(e.target.value as Role)}
        />
        <Button variant="primary" onClick={() => create.mutate()} disabled={create.isPending}>
          Crear enlace
        </Button>
      </div>
      <RoleSummary role={role} />
      {create.data?.url && (
        <>
          <p className={styles.link}>{create.data.url}</p>
          <Button onClick={() => void navigator.clipboard.writeText(create.data.url ?? "")}>
            Copiar enlace
          </Button>
        </>
      )}
      {(pending.data?.length ?? 0) > 0 && (
        <ul className={styles.list} aria-label="Invitaciones pendientes">
          {pending.data?.map((i) => (
            <li key={i.id} className={styles.row}>
              <div className={styles.grow}>
                {ROLE_OPTIONS.find((o) => o.value === i.role)?.label} · caduca el{" "}
                {format.format(new Date(i.expires_at))}
              </div>
              <Button variant="ghost" onClick={() => revoke.mutate(i.id)}>
                Anular
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function NewSpaceCard() {
  const { setSpace, refresh } = useSession();
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => api.createSpace(name),
    onSuccess: async (space) => {
      setName("");
      await refresh();
      setSpace(space.id);
    },
  });
  return (
    <Card title="Nuevo espacio">
      <form
        className={styles.inline}
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <TextField
          label="Nombre"
          placeholder="Familia"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className={styles.grow}
          required
        />
        <Button type="submit" disabled={create.isPending}>
          Crear
        </Button>
      </form>
      {create.isError && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
    </Card>
  );
}
