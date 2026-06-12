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

const pad2 = (n: number) => String(n).padStart(2, "0");

function hostnameOf(url: string | null): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function relPoll(iso: string | null): string {
  if (!iso) return "never polled";
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const mins = Math.round(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

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
  const [refreshing, setRefreshing] = useState(false);

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

  const refresh = async () => {
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <aside className="feed-sidebar">
      <div className="section-head">
        <span className="eyebrow eyebrow-ink">00 — Index / Feeds</span>
        <span className="counter">{pad2(feeds.length)}</span>
      </div>

      <ul className="feed-list">
        <li>
          <button
            type="button"
            className={`feed-row all ${selectedFeedId === null ? "active" : ""}`}
            onClick={() => onSelect(null)}
          >
            <span className="feed-row-index">★</span>
            <span>
              <span className="feed-row-title">All dispatches</span>
              <span className="feed-row-sub">Unified stream · All feeds</span>
            </span>
          </button>
        </li>
        {feeds.map((f, i) => (
          <li key={f.id}>
            <div
              className={`feed-row ${selectedFeedId === f.id ? "active" : ""}`}
              onClick={() => onSelect(f.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(f.id);
                }
              }}
            >
              <span className="feed-row-index">{pad2(i + 1)}</span>
              <span>
                <span className="feed-row-title">{f.title}</span>
                <span className="feed-row-sub">
                  {hostnameOf(f.site_url ?? f.url)} · {relPoll(f.last_polled)}
                </span>
              </span>
              <button
                type="button"
                className="feed-row-delete"
                onClick={(e) => {
                  e.stopPropagation();
                  void onDelete(f.id);
                }}
                aria-label={`Remove ${f.title}`}
              >
                ×
              </button>
            </div>
          </li>
        ))}
      </ul>

      <button
        type="button"
        className="btn btn-ghost"
        onClick={() => void refresh()}
        disabled={refreshing}
      >
        <span>{refreshing ? "Polling…" : "Refresh all"}</span>
        <span className="btn-arrow">↻</span>
      </button>

      <form onSubmit={submit} className="feed-form corner-marks">
        <span className="eyebrow eyebrow-ink">01 — Commit new feed</span>
        <div>
          <label className="feed-form-label" htmlFor="feed-url">
            URL
          </label>
          <input
            id="feed-url"
            placeholder="https://example.com/feed.xml"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="feed-form-label" htmlFor="feed-title">
            Title
          </label>
          <input
            id="feed-title"
            placeholder="Short label"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
        </div>
        <button type="submit" className="btn" disabled={busy}>
          <span>{busy ? "Committing…" : "Commit feed"}</span>
          <span className="btn-arrow">→</span>
        </button>
      </form>
    </aside>
  );
}
