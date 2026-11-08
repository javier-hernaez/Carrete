import type { ReactNode } from "react";

import { Logo } from "../../design-system/components/Logo";
import styles from "./auth.module.css";

export function AuthLayout({
  title,
  intro,
  children,
}: {
  title: string;
  intro?: ReactNode;
  children: ReactNode;
}) {
  return (
    <main className={styles.page}>
      <div className={styles.panel}>
        <div className={styles.brand}>
          <Logo />
        </div>
        <h1 className={styles.title}>{title}</h1>
        {intro && <div className={styles.intro}>{intro}</div>}
        {children}
      </div>
    </main>
  );
}
