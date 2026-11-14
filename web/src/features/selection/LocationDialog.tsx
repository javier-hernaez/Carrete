import { useState } from "react";

import { Button } from "../../design-system/components/Button";
import { Dialog } from "../../design-system/components/Dialog";
import { TextField } from "../../design-system/components/Field";
import { parseCoordinates } from "./coordinates";
import styles from "./selection.module.css";

/** Poner o quitar la ubicación a mano: p. ej. a las fotos de WhatsApp, que no la traen. */
export function LocationDialog({
  count,
  onSet,
  onClose,
}: {
  count: number;
  onSet: (coords: { lat: number; lon: number } | null) => void;
  onClose: () => void;
}) {
  const [value, setValue] = useState("");
  const coords = parseCoordinates(value);
  return (
    <Dialog title={count === 1 ? "Poner la ubicación" : `Poner la ubicación de ${count}`} onClose={onClose}>
      <div className={styles.form}>
        <TextField
          label="Coordenadas"
          placeholder="40.4168, -3.7038"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          hint="Latitud y longitud, separadas por una coma. Cópialas de cualquier mapa."
          error={value && !coords ? "No parecen unas coordenadas válidas" : undefined}
        />
        <Button variant="primary" disabled={!coords} onClick={() => onSet(coords)}>
          Guardar
        </Button>
        <Button variant="ghost" onClick={() => onSet(null)}>
          Quitar la ubicación
        </Button>
      </div>
    </Dialog>
  );
}
