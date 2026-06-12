"use client";

import { useEffect, useRef } from "react";

type Props = {
  open: boolean;
  title: string;
  body: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = "Delete",
  onConfirm,
  onCancel,
}: Props) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    confirmRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div className="dialog-overlay" onClick={onCancel}>
      <div
        className="dialog corner-marks"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <p className="eyebrow eyebrow-ink">Confirm</p>
        <h3 className="dialog-title">{title}</h3>
        <p className="dialog-body">{body}</p>
        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            <span>Cancel</span>
          </button>
          <button type="button" ref={confirmRef} className="btn btn-danger" onClick={onConfirm}>
            <span>{confirmLabel}</span>
            <span className="btn-arrow">→</span>
          </button>
        </div>
      </div>
    </div>
  );
}
