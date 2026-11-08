import { useSession } from "./session";
import styles from "./AppShell.module.css";

/** Cambio de espacio: discreto, en la cabecera. Con un solo espacio solo se muestra su nombre. */
export function SpaceSwitcher() {
  const { me, space, setSpace } = useSession();
  const active = me.spaces.filter((s) => !s.archived || s.id === space?.id);
  if (active.length <= 1) return space ? <span className={styles.spaceName}>{space.name}</span> : null;
  return (
    <>
      <label htmlFor="space-switcher" className="visually-hidden">
        Espacio
      </label>
      <select
        id="space-switcher"
        className={styles.spaceSelect}
        value={space?.id ?? ""}
        onChange={(e) => setSpace(e.target.value)}
      >
        {active.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
    </>
  );
}
