import type { ReviewMode } from "./mode";
import styles from "./review.module.css";

export function ModeSwitch({
  mode,
  onMode,
  dark = false,
}: {
  mode: ReviewMode;
  onMode: (mode: ReviewMode) => void;
  dark?: boolean;
}) {
  return (
    <div className={dark ? styles.modeDark : styles.mode} role="group" aria-label="Cómo revisar">
      <button type="button" aria-pressed={mode === "grid"} onClick={() => onMode("grid")}>
        En bloque
      </button>
      <button type="button" aria-pressed={mode === "one"} onClick={() => onMode("one")}>
        Una a una
      </button>
    </div>
  );
}
