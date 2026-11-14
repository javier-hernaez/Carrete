import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";
import { errorMessage, UserError } from "../../app/errors";
import { useSession } from "../../app/session";
import { Button } from "../../design-system/components/Button";
import { Alert, Card } from "../../design-system/components/Card";
import { TextField } from "../../design-system/components/Field";
import styles from "../page.module.css";
import { creationOptions, credentialToJson, passkeyError, passkeysSupported } from "./webauthn";

const date = new Intl.DateTimeFormat("es", { dateStyle: "medium" });

/** Llaves de acceso: entrar con la huella o la cara del móvil, sin contraseña ni código. */
export function PasskeysCard() {
  const { withReauth } = useSession();
  const queryClient = useQueryClient();
  const keys = useQuery({ queryKey: ["passkeys"], queryFn: api.passkeys });
  const [name, setName] = useState("");
  const [error, setError] = useState<string>();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["passkeys"] });
  const add = useMutation({
    mutationFn: async () => {
      const { challenge_id, options } = await api.passkeyRegisterOptions();
      let credential: Credential | null;
      try {
        credential = await navigator.credentials.create({ publicKey: creationOptions(options) });
      } catch (e) {
        throw new UserError(passkeyError(e));
      }
      if (!(credential instanceof PublicKeyCredential)) throw new UserError("No se creó ninguna llave");
      return api.passkeyRegister(
        challenge_id,
        credentialToJson(credential),
        name.trim() || "Llave de acceso",
      );
    },
    onSuccess: async () => {
      setName("");
      setError(undefined);
      await refresh();
    },
    onError: (e) => setError(errorMessage(e)),
  });
  if (!passkeysSupported()) return null;
  return (
    <Card title="Llaves de acceso">
      <p className={styles.muted}>
        Entra con la huella, la cara o el PIN del dispositivo en lugar de la contraseña y el código. Tu
        contraseña y la verificación en dos pasos siguen valiendo.
      </p>
      {error && <Alert tone="danger">{error}</Alert>}
      {(keys.data?.length ?? 0) > 0 && (
        <ul className={styles.list}>
          {keys.data?.map((k) => (
            <li key={k.id} className={styles.row}>
              <div className={styles.grow}>
                <strong>{k.name}</strong>
                <div className={styles.muted}>
                  Creada el {date.format(new Date(k.created_at))} ·{" "}
                  {k.last_used_at ? `usada el ${date.format(new Date(k.last_used_at))}` : "sin usar"}
                </div>
              </div>
              <Button
                variant="ghost"
                onClick={() =>
                  void withReauth(() => api.passkeyDelete(k.id))
                    .then(refresh)
                    .catch((e: unknown) => setError(errorMessage(e)))
                }
              >
                Quitar
              </Button>
            </li>
          ))}
        </ul>
      )}
      <form
        className={styles.form}
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate();
        }}
      >
        <TextField
          label="Nombre de la llave"
          placeholder="Mi móvil"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={80}
        />
        <Button type="submit" disabled={add.isPending}>
          Añadir una llave de acceso
        </Button>
      </form>
    </Card>
  );
}
