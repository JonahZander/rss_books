"use client";

import { useState } from "react";
import type { Feed } from "../lib/api";

type Props = {
  feeds: Feed[];
  selectedFeedId: number | null;
  onSelect: (id: number | null) => void;
  onAdd: (url: string, title: string) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  onRefresh: () => Promise<void>;
};

export function FeedSidebar({
  feeds,
  selectedFeedId,
  onSelect,
  onAdd,
  onDelete,
  onRefresh,
}: Props) {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url || !title) return;
    setBusy(true);
    try {
      await onAdd(url, title);
      setUrl("");
      setTitle("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="feed-sidebar">
      <div className="sidebar-header">
        <h2>Feeds</h2>
        <button onClick={() => void onRefresh()} disabled={busy}>
          Refresh
        </button>
      </div>
      <ul className="feed-list">
        <li>
          <button
            className={selectedFeedId === null ? "active" : ""}
            onClick={() => onSelect(null)}
          >
            All feeds
          </button>
        </li>
        {feeds.map((f) => (
          <li key={f.id}>
            <button
              className={selectedFeedId === f.id ? "active" : ""}
              onClick={() => onSelect(f.id)}
            >
              {f.title}
            </button>
            <button
              className="delete"
              onClick={() => void onDelete(f.id)}
              aria-label="delete"
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={submit} className="feed-form">
        <input
          placeholder="RSS URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
        />
        <input
          placeholder="Title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
        />
        <button type="submit" disabled={busy}>
          Add feed
        </button>
      </form>
    </aside>
  );
}
