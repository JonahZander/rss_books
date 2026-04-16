"use client";

import { useState } from "react";
import type { Article, Digest } from "../lib/api";
import { api } from "../lib/api";

type Props = {
  selected: Article[];
  onClear: () => void;
};

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

  return (
    <section className="digest-queue">
      <h3>Digest ({selected.length})</h3>
      <ul>
        {selected.map((a) => (
          <li key={a.id}>{a.title}</li>
        ))}
      </ul>
      <button onClick={() => void send()} disabled={selected.length === 0 || sending}>
        {sending ? "Building…" : "Build digest"}
      </button>
      {error && <p className="error">{error}</p>}
      {digest && digest.status === "ready" && (
        <a href={api.downloadDigestUrl(digest.id)} className="download-link">
          Download {digest.title}.epub
        </a>
      )}
      {selected.length > 0 && (
        <button className="secondary" onClick={onClear}>
          Clear selection
        </button>
      )}
    </section>
  );
}
