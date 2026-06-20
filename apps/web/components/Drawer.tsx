"use client";

import { useEffect, useRef, type ReactNode } from "react";

/** Right-side slide-over panel. Presentational: the parent owns `open` and the
 * content. Closes on Escape or backdrop click; traps initial focus on itself. */
export function Drawer({
  open,
  eyebrow,
  title,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  eyebrow?: string;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <aside
        ref={panelRef}
        tabIndex={-1}
        className="drawer corner-marks"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="drawer-head">
          <div className="drawer-headings">
            {eyebrow && <p className="eyebrow eyebrow-ink">{eyebrow}</p>}
            <h3 className="drawer-title">{title}</h3>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
            <span>Close</span>
            <span className="btn-arrow">×</span>
          </button>
        </header>
        <div className="drawer-body">{children}</div>
        {footer && <footer className="drawer-foot">{footer}</footer>}
      </aside>
    </div>
  );
}
