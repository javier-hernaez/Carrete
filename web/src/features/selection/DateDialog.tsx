import { useState } from "react";

import { Button } from "../../design-system/components/Button";
import { Dialog } from "../../design-system/components/Dialog";
import { SelectField, TextField } from "../../design-system/components/Field";
import styles from "./selection.module.css";

/** Corregir la fecha: fijarla o moverla N horas o días. El original no se toca. */
export function DateDialog({
  count,
  initial,
  onSet,
  onShift,
  onClose,
}: {
  count: number;
  initial?: string | undefined;
  onSet: (takenAt: string) => void;
  onShift: (minutes: number) => void;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<"set" | "shift">(count === 1 ? "set" : "shift");
  const [value, setValue] = useState((initial ?? "").slice(0, 16));
  const [amount, setAmount] = useState("1");
  const [unit, setUnit] = useState("hours");
  const [direction, setDirection] = useState("-1");
  const minutes = Math.round(Number(amount) * (unit === "days" ? 1440 : 60) * Number(direction));
  return (
    <Dialog title={count === 1 ? "Cambiar la fecha" : `Cambiar la fecha de ${count}`} onClose={onClose}>
      <div className={styles.form}>
        <div className={styles.segmented} role="radiogroup" aria-label="Cómo cambiarla">
          <label>
            <input type="radio" name="modo" checked={mode === "set"} onChange={() => setMode("set")} /> Fijar
            fecha y hora
          </label>
          <label>
            <input type="radio" name="modo" checked={mode === "shift"} onChange={() => setMode("shift")} />{" "}
            Mover
          </label>
        </div>
        {mode === "set" ? (
          <TextField
            label="Fecha y hora de la foto"
            type="datetime-local"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            hint="Hora del lugar donde se hizo la foto."
          />
        ) : (
          <div className={styles.inline}>
            <SelectField
              label="Hacia"
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
              options={[
                { value: "-1", label: "Antes" },
                { value: "1", label: "Después" },
              ]}
            />
            <TextField
              label="Cuánto"
              type="number"
              min="1"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            <SelectField
              label="Unidad"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
              options={[
                { value: "hours", label: "horas" },
                { value: "days", label: "días" },
              ]}
            />
          </div>
        )}
        <Button
          variant="primary"
          disabled={mode === "set" ? !value : !minutes}
          onClick={() =>
            mode === "set" ? onSet(value.length === 16 ? `${value}:00` : value) : onShift(minutes)
          }
        >
          Guardar
        </Button>
      </div>
    </Dialog>
  );
}
