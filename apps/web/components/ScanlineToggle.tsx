"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "rks-scanlines";

/**
 * Client-only toggle for the CRT scanline overlay. The preference lives in
 * localStorage (it's a purely visual choice, not server state) and is applied
 * by toggling `.scanlines-off` on <html>; a pre-paint script in layout.tsx
 * sets the same class on load to avoid a flash.
 */
export function ScanlineToggle() {
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    // Sync from localStorage once on mount (the pre-paint script already set
    // the class; this just aligns React's checkbox state).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEnabled(localStorage.getItem(STORAGE_KEY) !== "off");
  }, []);

  const onChange = (next: boolean) => {
    setEnabled(next);
    localStorage.setItem(STORAGE_KEY, next ? "on" : "off");
    document.documentElement.classList.toggle("scanlines-off", !next);
  };

  return (
    <label className="filter-toggle">
      <input
        type="checkbox"
        className="checkbox"
        checked={enabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>Show the CRT scanline overlay</span>
    </label>
  );
}
