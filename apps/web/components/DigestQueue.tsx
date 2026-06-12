"use client";

import { useState } from "react";
import type { Article, Digest } from "../lib/api";
import { api } from "../lib/api";
import { useToast } from "./Toasts";

type Props = {
  queue: Article[];
  emailConfigured: boolean;
  onRemove: (article: Article) => void;
  onClear: () => void;
  onCompiled: () => Promise<void>;
};

const pad2 = (n: number) => String(n).padStart(2, "0");

export function DigestQueue({ queue, emailConfigured, onRemove, onClear, onCompiled }: Props) {
  const toast = useToast();
  const [digest, setDigest] = useState<Digest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [compiling, setCompiling] = useState(false);
  const [sending, setSending] = useState(false);

  const compile = async () => {
    if (queue.length === 0) return;
    setCompiling(true);
    setError(null);
    try {
      const d = await api.createDigest();
      setDigest(d);
      let current = d;
      while (current.status === "pending" || current.status === "generating") {
        await new Promise((r) => setTimeout(r, 1000));
        current = await api.getDigest(d.id);
        setDigest(current);
      }
      if (current.status === "failed") {
        setError(current.error ?? "digest build failed");
        toast("Edition failed to build", "error");
      } else {
        toast(`Edition ${current.title} is ready`);
      }
      await onCompiled();
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed");
    } finally {
      setCompiling(false);
    }
  };

  const send = async () => {
    if (!digest) return;
    setSending(true);
    try {
      const delivery = await api.sendDigest(digest.id);
      if (delivery.status === "sent") {
        toast(`Emailed to ${delivery.target}`);
      } else {
        toast(delivery.error ?? "send failed", "error");
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : "send failed", "error");
    } finally {
      setSending(false);
    }
  };

  const count = queue.length;
  const statusLabel =
    digest?.status === "ready"
      ? "Ready · EPUB committed"
      : digest?.status === "failed"
        ? "Failed"
        : digest?.status === "generating"
          ? "Generating EPUB…"
          : digest?.status === "pending"
            ? "Pending"
            : null;

  return (
    <section className="digest-queue" aria-label="Digest queue">
      <div className="section-head">
        <span className="eyebrow eyebrow-ink">03 — Dispatch / Digest</span>
      </div>

      <div className="queue-readout">
        <span className={`queue-count ${count > 0 ? "armed" : ""}`}>{pad2(count)}</span>
        <div className="queue-count-sub">
          <span className="queue-count-label">Queued</span>
          <span className="queue-count-hint">
            {count === 1 ? "article" : "articles"} · survives reload
          </span>
        </div>
      </div>

      {count === 0 ? (
        <p className="queue-empty">Queue empty · Tick articles to compile</p>
      ) : (
        <ol className="queue-list">
          {queue.map((a, i) => (
            <li key={a.id}>
              <span className="q-idx">{pad2(i + 1)}</span>
              <span className="q-title">{a.title}</span>
              <button
                type="button"
                className="feed-tool danger"
                aria-label={`Remove ${a.title} from queue`}
                onClick={() => onRemove(a)}
              >
                ×
              </button>
            </li>
          ))}
        </ol>
      )}

      <div className="queue-actions">
        <button
          type="button"
          className="btn"
          onClick={() => void compile()}
          disabled={count === 0 || compiling}
        >
          <span>{compiling ? "Compiling…" : "Compile · EPUB"}</span>
          <span className="btn-arrow">→</span>
        </button>

        {count > 0 && !compiling && (
          <button type="button" className="btn btn-ghost" onClick={onClear}>
            <span>Clear queue</span>
            <span className="btn-arrow">×</span>
          </button>
        )}
      </div>

      {statusLabel && (
        <div
          className={`queue-status ${
            digest?.status === "generating" || digest?.status === "pending"
              ? "generating"
              : digest?.status === "ready"
                ? "ready"
                : "failed"
          }`}
        >
          <div className="queue-status-row">
            <span>{statusLabel}</span>
          </div>
          {digest && (
            <span className="queue-status-ref">
              Ref&nbsp;#{String(digest.id).padStart(4, "0")} · {digest.title}
            </span>
          )}
        </div>
      )}

      {error && <p className="article-body-error">⚠ {error}</p>}

      {digest && digest.status === "ready" && (
        <>
          <a href={api.downloadDigestUrl(digest.id)} className="queue-download" download>
            <span>Download · {digest.title}.epub</span>
            <span className="queue-download-arrow">↓</span>
          </a>
          {emailConfigured && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => void send()}
              disabled={sending}
            >
              <span>{sending ? "Sending…" : "Send to e-reader"}</span>
              <span className="btn-arrow">✉</span>
            </button>
          )}
        </>
      )}
    </section>
  );
}
