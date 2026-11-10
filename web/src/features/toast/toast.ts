/** Avisos breves con acción opcional («Deshacer»). Viven fuera de React, como la cola de subida. */

export interface Toast {
  id: number;
  message: string;
  action?: { label: string; run: () => Promise<unknown> | undefined } | undefined;
  tone: "info" | "danger";
}

type Listener = () => void;

let toasts: Toast[] = [];
let nextId = 1;
const listeners = new Set<Listener>();

function emit() {
  listeners.forEach((l) => {
    l();
  });
}

export const toastStore = {
  subscribe: (listener: Listener) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  get: () => toasts,
};

export function showToast(
  message: string,
  options: { action?: Toast["action"]; tone?: Toast["tone"]; ms?: number } = {},
) {
  const toast: Toast = { id: nextId++, message, action: options.action, tone: options.tone ?? "info" };
  toasts = [...toasts.slice(-2), toast];
  emit();
  setTimeout(
    () => {
      dismissToast(toast.id);
    },
    options.ms ?? (options.action ? 8000 : 4000),
  );
  return toast.id;
}

export function dismissToast(id: number) {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}
