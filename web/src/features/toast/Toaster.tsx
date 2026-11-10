import { useSyncExternalStore } from "react";

import { dismissToast, toastStore } from "./toast";
import styles from "./toast.module.css";

export function Toaster() {
  const toasts = useSyncExternalStore(toastStore.subscribe, toastStore.get);
  return (
    <div className={styles.region} role="status" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`${styles.toast ?? ""} ${t.tone === "danger" ? (styles.danger ?? "") : ""}`}
        >
          <span>{t.message}</span>
          {t.action && (
            <button
              type="button"
              className={styles.action}
              onClick={() => {
                dismissToast(t.id);
                void t.action?.run();
              }}
            >
              {t.action.label}
            </button>
          )}
          <button
            type="button"
            className={styles.close}
            aria-label="Cerrar aviso"
            onClick={() => dismissToast(t.id)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
