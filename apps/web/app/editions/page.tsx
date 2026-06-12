"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { Masthead } from "../../components/Masthead";
import { useToast } from "../../components/Toasts";
import { api, emailConfigured, type AppSettings, type Digest } from "../../lib/api";

function fmtSize(bytes: number | null): string {
  if (!bytes) return "—";
  return bytes >= 2 ** 20 ? `${(bytes / 2 ** 20).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
}

function fmtDate(iso: string): string {
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(
    d.getDate(),
  ).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(
    2,
    "0",
  )}`;
}

const STATUS_LABEL: Record<Digest["status"], string> = {
  pending: "Pending",
  generating: "Generating",
  ready: "Ready",
  failed: "Failed",
};

export default function Editions() {
  const toast = useToast();
  const [digests, setDigests] = useState<Digest[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Digest | null>(null);
  const [sendingId, setSendingId] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    setDigests(await api.listDigests());
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
    api.getSettings().then(setSettings, () => {});
  }, [refresh]);

  const busy = digests.some((d) => d.status === "pending" || d.status === "generating");
  useEffect(() => {
    if (!busy) return;
    const id = window.setInterval(() => void refresh(), 1500);
    return () => window.clearInterval(id);
  }, [busy, refresh]);

  const send = async (digest: Digest) => {
    setSendingId(digest.id);
    try {
      const delivery = await api.sendDigest(digest.id);
      if (delivery.status === "sent") {
        toast(`Edition ${digest.title} emailed to ${delivery.target}`);
      } else {
        toast(delivery.error ?? "send failed", "error");
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : "send failed", "error");
    } finally {
      setSendingId(null);
      await refresh();
    }
  };

  const remove = async () => {
    if (!deleteTarget) return;
    const digest = deleteTarget;
    setDeleteTarget(null);
    try {
      await api.deleteDigest(digest.id);
      toast(`Edition ${digest.title} deleted`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "delete failed", "error");
    }
    await refresh();
  };

  const canEmail = settings ? emailConfigured(settings) : false;

  return (
    <div className="app">
      <Masthead />
      <main className="page-main" aria-label="Editions">
        <div className="content-head">
          <div>
            <span className="eyebrow">04 — Pressed editions</span>
            <h2 className="content-title">Editions</h2>
          </div>
          <div className="content-meta">
            <span>
              Total <strong>{String(digests.length).padStart(2, "0")}</strong>
            </span>
          </div>
        </div>

        {digests.length === 0 ? (
          <p className="empty-state">
            No editions pressed yet
            <small>Queue articles on the triage desk and compile.</small>
          </p>
        ) : (
          <ul className="edition-list">
            {digests.map((d) => (
              <li key={d.id} className={`edition-row status-${d.status}`}>
                <div className="edition-main">
                  <span className="edition-ref">#{String(d.id).padStart(4, "0")}</span>
                  <div className="edition-titleblock">
                    <span className="edition-title">{d.title}</span>
                    <span className="edition-sub">
                      {fmtDate(d.created_at)} · {d.article_count}{" "}
                      {d.article_count === 1 ? "article" : "articles"} · {fmtSize(d.size_bytes)}
                    </span>
                    {d.status === "failed" && d.error && (
                      <span className="edition-error">⚠ {d.error}</span>
                    )}
                    {d.deliveries.length > 0 && (
                      <span className="edition-deliveries">
                        {d.deliveries[0].status === "sent" ? "✓ emailed" : "✗ email failed"} ·{" "}
                        {fmtDate(d.deliveries[0].created_at)}
                        {d.deliveries[0].status === "failed" && d.deliveries[0].error
                          ? ` — ${d.deliveries[0].error}`
                          : ""}
                      </span>
                    )}
                  </div>
                  <span className={`status-chip chip-${d.status}`}>{STATUS_LABEL[d.status]}</span>
                </div>
                <div className="edition-actions">
                  {d.status === "ready" && (
                    <a className="btn btn-ghost btn-sm" href={api.downloadDigestUrl(d.id)} download>
                      <span>Download</span>
                      <span className="btn-arrow">↓</span>
                    </a>
                  )}
                  {d.status === "ready" && canEmail && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      disabled={sendingId === d.id}
                      onClick={() => void send(d)}
                    >
                      <span>{sendingId === d.id ? "Sending…" : "Send"}</span>
                      <span className="btn-arrow">✉</span>
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm danger"
                    onClick={() => setDeleteTarget(d)}
                  >
                    <span>Delete</span>
                    <span className="btn-arrow">×</span>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </main>
      <ConfirmDialog
        open={deleteTarget !== null}
        title={`Delete edition ${deleteTarget?.title ?? ""}?`}
        body="The edition and its EPUB file will be removed. Articles stay in your library."
        confirmLabel="Delete edition"
        onConfirm={() => void remove()}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
