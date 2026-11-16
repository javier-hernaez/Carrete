import { ADMIN_NOTE, ROLE_INFO, ROLE_OPTIONS } from "./roles";
import type { Role } from "../api/client";
import styles from "./RoleHelp.module.css";

/** Lo que puede hacer una persona con un rol concreto (al invitar o al aceptar una invitación). */
export function RoleSummary({ role }: { role: Role }) {
  const info = ROLE_INFO[role];
  return (
    <div className={styles.summary}>
      <p>{info.summary}</p>
      <ul>
        {info.can.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

/** Desplegable con los tres roles, para consultar cuando haga falta. */
export function RoleHelp() {
  return (
    <details className={styles.help}>
      <summary>¿Qué puede hacer cada rol?</summary>
      <dl>
        {ROLE_OPTIONS.map((o) => (
          <div key={o.value}>
            <dt>{o.label}</dt>
            <dd>
              <RoleSummary role={o.value} />
            </dd>
          </div>
        ))}
      </dl>
      <p className={styles.note}>{ADMIN_NOTE}</p>
    </details>
  );
}
