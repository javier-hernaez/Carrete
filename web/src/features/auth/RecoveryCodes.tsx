import { Button } from "../../design-system/components/Button";
import styles from "./auth.module.css";

/** Muestra los códigos de recuperación una sola vez, con opción de copiarlos o descargarlos. */
export function RecoveryCodes({
  codes,
  onDone,
  doneLabel,
}: {
  codes: string[];
  onDone?: () => void;
  doneLabel?: string;
}) {
  const text = codes.join("\n");
  const download = () => {
    const url = URL.createObjectURL(
      new Blob([`Códigos de recuperación de Carrete\n\n${text}\n`], { type: "text/plain" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "carrete-codigos-de-recuperacion.txt";
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className={styles.form}>
      <p>
        Guarda estos códigos en un lugar seguro. Cada uno sirve <strong>una sola vez</strong> para entrar si
        pierdes el móvil. No se volverán a mostrar.
      </p>
      <ul className={styles.codes} aria-label="Códigos de recuperación">
        {codes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <Button onClick={() => void navigator.clipboard.writeText(text)}>Copiar</Button>
      <Button onClick={download}>Descargar</Button>
      {onDone && (
        <Button variant="primary" onClick={onDone}>
          {doneLabel ?? "Ya los he guardado"}
        </Button>
      )}
    </div>
  );
}
