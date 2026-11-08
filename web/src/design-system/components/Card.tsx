import { useId, type ReactNode } from "react";

import styles from "./Card.module.css";

export function Card({
  title,
  children,
  actions,
}: {
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  const id = useId();
  return (
    <section className={styles.card} aria-labelledby={title ? id : undefined}>
      {(title || actions) && (
        <header className={styles.header}>
          {title && (
            <h2 id={id} className={styles.title}>
              {title}
            </h2>
          )}
          {actions}
        </header>
      )}
      <div className={styles.body}>{children}</div>
    </section>
  );
}

export function Alert({
  tone = "info",
  children,
}: {
  tone?: "info" | "danger" | "success" | "warning";
  children: ReactNode;
}) {
  return (
    <div
      className={`${styles.alert ?? ""} ${styles[tone] ?? ""}`}
      role={tone === "danger" ? "alert" : "status"}
    >
      {children}
    </div>
  );
}

export function PageTitle({ children, actions }: { children: ReactNode; actions?: ReactNode }) {
  return (
    <div className={styles.pageTitle}>
      <h1 className={styles.h1}>{children}</h1>
      {actions}
    </div>
  );
}
