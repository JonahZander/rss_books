"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

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
  // Portal to <body>: the drawer is rendered inside an animated (transformed)
  // panel, which would otherwise make position:fixed relative to that panel
  // instead of the viewport — clipping the drawer into a tiny box.
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // Defer portal to the client so SSR/static-export markup matches.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || !mounted) return null;

  return createPortal(
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
    </div>,
    document.body,
  );
}
