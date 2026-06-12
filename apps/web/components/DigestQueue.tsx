"use client";

import { useState } from "react";
import type { Article, Digest } from "../lib/api";
import { api } from "../lib/api";

type Props = {
  selected: Article[];
  onClear: () => void;
};

const pad2 = (n: number) => String(n).padStart(2, "0");

export function DigestQueue({ selected, onClear }: Props) {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const send = async () => {
    if (selected.length === 0) return;
    setSending(true);
    setError(null);
    try {
      const d = await api.createDigest(selected.map((a) => a.id));
      setDigest(d);
      let current = d;
      while (current.status !== "ready") {
        await new Promise((r) => setTimeout(r, 1000));
        current = await api.getDigest(d.id);
        setDigest(current);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed");
    } finally {
      setSending(false);
    }
  };

  const count = selected.length;
  const statusLabel =
    digest?.status === "ready"
      ? "Ready · EPUB committed"
      : digest?.status === "generating"
        ? "Generating EPUB…"
        : digest?.status === "pending"
          ? "Pending"
          : null;

  return (
    <section className="digest-queue">
      <div className="section-head">
        <span className="eyebrow eyebrow-ink">03 — Dispatch / Digest</span>
      </div>

      <div className="queue-readout">
        <span className="queue-count">{pad2(count)}</span>
        <div className="queue-count-sub">
          <span className="queue-count-label">Selected</span>
          <span className="queue-count-hint">{count === 1 ? "article" : "articles"} queued</span>
        </div>
      </div>

      {count === 0 ? (
        <p className="queue-empty">Queue empty · Select articles to compile</p>
      ) : (
        <ol className="queue-list">
          {selected.map((a, i) => (
            <li key={a.id}>
              <span className="q-idx">{pad2(i + 1)}</span>
              <span>{a.title}</span>
            </li>
          ))}
        </ol>
      )}

      <div className="queue-actions">
        <button
          type="button"
          className="btn"
          onClick={() => void send()}
          disabled={count === 0 || sending}
        >
          <span>{sending ? "Compiling…" : "Compile · EPUB"}</span>
          <span className="btn-arrow">→</span>
        </button>

        {count > 0 && !sending && (
          <button type="button" className="btn btn-ghost" onClick={onClear}>
            <span>Clear queue</span>
            <span className="btn-arrow">×</span>
          </button>
        )}
      </div>

      {statusLabel && (
        <div
          className={`queue-status ${
            digest?.status === "generating" ? "generating" : digest?.status === "ready" ? "ready" : ""
          }`}
        >
          <div className="queue-status-row">
            <span>{statusLabel}</span>
          </div>
          {digest && (
            <span style={{ color: "var(--ink-3)", fontSize: 9.5, letterSpacing: "0.1em" }}>
              Ref&nbsp;#{String(digest.id).padStart(4, "0")} · {digest.title}
            </span>
          )}
        </div>
      )}

      {error && <p className="article-body-error">⚠ {error}</p>}

      {digest && digest.status === "ready" && (
        <a href={api.downloadDigestUrl(digest.id)} className="queue-download" download>
          <span>Download · {digest.title}.epub</span>
          <span className="queue-download-arrow">↓</span>
        </a>
      )}
    </section>
  );
}
