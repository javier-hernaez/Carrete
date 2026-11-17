import type { Tag } from "../../api/client";
import { cx } from "../../design-system/cx";
import styles from "./tags.module.css";

/**
 * Fichas para filtrar por etiquetas. Varias a la vez: elementos que las tienen todas.
 * «Sin etiqueta» es excluyente con las demás.
 */
export function TagFilter({
  tags,
  selected,
  untagged,
  onChange,
  label = "Filtrar por etiqueta",
}: {
  tags: Tag[];
  selected: string[];
  untagged: boolean;
  onChange: (next: { selected: string[]; untagged: boolean }) => void;
  label?: string;
}) {
  if (tags.length === 0) return null;
  const toggle = (id: string) =>
    onChange({
      selected: selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id],
      untagged: false,
    });
  const any = selected.length > 0 || untagged;
  return (
    <div className={styles.filter} role="group" aria-label={label}>
      <button
        type="button"
        className={cx(styles.chip, !any && styles.chipOn)}
        aria-pressed={!any}
        onClick={() => onChange({ selected: [], untagged: false })}
      >
        Todas
      </button>
      {tags.map((tag) => (
        <button
          key={tag.id}
          type="button"
          className={cx(styles.chip, selected.includes(tag.id) && styles.chipOn)}
          aria-pressed={selected.includes(tag.id)}
          onClick={() => toggle(tag.id)}
        >
          {tag.name}
          <span className={styles.chipCount}>{tag.count}</span>
        </button>
      ))}
      <button
        type="button"
        className={cx(styles.chip, untagged && styles.chipOn)}
        aria-pressed={untagged}
        onClick={() => onChange({ selected: [], untagged: !untagged })}
      >
        Sin etiqueta
      </button>
    </div>
  );
}
