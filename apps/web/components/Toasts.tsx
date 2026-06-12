"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

type Variant = "ok" | "error";
type Toast = { id: number; msg: string; variant: Variant; leaving: boolean };

const ToastContext = createContext<(msg: string, variant?: Variant) => void>(() => {});

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const push = useCallback((msg: string, variant: Variant = "ok") => {
    const id = nextId.current++;
    setToasts((prev) => [...prev, { id, msg, variant, leaving: false }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    }, 3600);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`toast ${t.variant === "error" ? "toast-error" : ""} ${
              t.leaving ? "leaving" : ""
            }`}
          >
            <span className="toast-square" aria-hidden />
            {t.msg}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
