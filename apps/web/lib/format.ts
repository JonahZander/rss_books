// Shared formatting helpers used across the triage desk, editions page,
// and presentational components. Keep output byte-identical when refactoring.

/** Strip tags and decode common entities from stored summary HTML. */
export function plainSummary(raw: string | null): string {
  if (!raw) return "";
  const withoutTags = raw.replace(/<[^>]*>/g, " ");
  const decoded = withoutTags
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)));
  return decoded.replace(/\s+/g, " ").trim();
}

/** Two-digit zero-padded counter, e.g. 7 → "07". */
export const pad2 = (n: number): string => String(n).padStart(2, "0");

/** Unread badges: keep 3 digits so counts never overflow the sidebar row. */
export function capCount(n: number): string {
  return n > 999 ? "999+" : String(n);
}

/** Local 24h time with seconds, or "never". */
export function hhmmss(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

/** Today's date as "YYYY.MM.DD". */
export function ymd(): string {
  const d = new Date();
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

/** "YYYY.MM.DD · HH:MM" for article timestamps. */
export function fmtTimestamp(iso: string): string {
  const d = new Date(iso);
  const date = `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
  const time = d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return `${date} · ${time}`;
}

/** "YYYY.MM.DD HH:MM" for edition timestamps (naive ISO treated as UTC). */
export function fmtDate(iso: string): string {
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(
    d.getDate(),
  ).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(
    2,
    "0",
  )}`;
}

/** File size as "N KB" / "N.N MB", or an em dash when unknown. */
export function fmtSize(bytes: number | null): string {
  if (!bytes) return "-";
  return bytes >= 2 ** 20 ? `${(bytes / 2 ** 20).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
}
