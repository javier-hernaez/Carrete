import { useId, type ReactNode } from "react";

import styles from "./EmptyState.module.css";
import { LogoMark } from "./Logo";

interface EmptyStateProps {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}

/** Estado vacío: el único sitio, junto al logotipo, donde la identidad del carrete se deja ver. */
export function EmptyState({ title, children, action }: EmptyStateProps) {
  const titleId = useId();
  return (
    <section className={styles.empty} aria-labelledby={titleId}>
      <div className={styles.mark}>
        <LogoMark size={56} />
      </div>
      <h2 id={titleId} className={styles.title}>
        {title}
      </h2>
      {children && <p className={styles.text}>{children}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </section>
  );
}
