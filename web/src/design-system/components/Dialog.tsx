import { useEffect, useId, useRef, type ReactNode } from "react";

import styles from "./Dialog.module.css";

/** Diálogo modal nativo (<dialog>): foco atrapado, Escape para cerrar y fondo inerte de serie. */
export function Dialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open && typeof dialog.showModal === "function") dialog.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={styles.dialog}
      aria-labelledby={id}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <header className={styles.header}>
        <h2 id={id} className={styles.title}>
          {title}
        </h2>
        <button type="button" className={styles.close} onClick={onClose} aria-label="Cerrar">
          ×
        </button>
      </header>
      {children}
    </dialog>
  );
}
