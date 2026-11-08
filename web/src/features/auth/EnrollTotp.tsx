import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api } from "../../api/client";
import { Button } from "../../design-system/components/Button";
import { Alert } from "../../design-system/components/Card";
import { TextField } from "../../design-system/components/Field";
import { errorMessage } from "../../app/errors";
import styles from "./auth.module.css";
import { RecoveryCodes } from "./RecoveryCodes";

/** Activación del segundo factor: QR, comprobación de un código y códigos de recuperación. */
export function EnrollTotp({ onDone }: { onDone: () => void }) {
  const setup = useQuery({
    queryKey: ["totp-setup"],
    queryFn: api.totpSetup,
    staleTime: Infinity,
    gcTime: 0,
  });
  const [code, setCode] = useState("");
  const enable = useMutation({ mutationFn: (c: string) => api.totpEnable(c) });

  if (enable.data) return <RecoveryCodes codes={enable.data.recovery_codes} onDone={onDone} />;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    enable.mutate(code);
  };

  return (
    <form className={styles.form} onSubmit={submit}>
      <ol>
        <li>Instala una app de autenticación (Google Authenticator, Aegis, 2FAS…).</li>
        <li>Escanea este código con ella.</li>
        <li>Escribe el número de 6 cifras que te muestra.</li>
      </ol>
      {setup.isError && <Alert tone="danger">{errorMessage(setup.error)}</Alert>}
      {setup.data && (
        <>
          {/* El SVG lo genera el servidor (segno) a partir de datos propios; no lleva contenido del usuario. */}
          <div
            className={styles.qr}
            role="img"
            aria-label="Código QR para la app de autenticación"
            dangerouslySetInnerHTML={{ __html: setup.data.qr_svg }}
          />
          <details>
            <summary>¿No puedes escanearlo? Escribe la clave a mano</summary>
            <p className={styles.secret}>{setup.data.secret}</p>
          </details>
        </>
      )}
      <TextField
        label="Código de 6 cifras"
        inputMode="numeric"
        autoComplete="one-time-code"
        pattern="[0-9 ]*"
        maxLength={7}
        value={code}
        onChange={(e) => setCode(e.target.value)}
        error={enable.isError ? errorMessage(enable.error) : undefined}
        required
      />
      <Button type="submit" variant="primary" disabled={enable.isPending || !setup.data}>
        Activar
      </Button>
    </form>
  );
}
