"use client";

import { type FormEvent, useState } from "react";
import Link from "next/link";
import type { Article, Digest } from "../lib/api";
import { api } from "../lib/api";
import { pad2 } from "../lib/format";
import { useToast } from "./Toasts";

type Props = {
  queue: Article[];
  emailConfigured: boolean;
  groupsExist: boolean;
  /** Render-profile names from settings; empty = feature not in use. */
  profiles: string[];
  /** Resolved default profile name from settings; null = no profiles exist. */
  defaultProfile: string | null;
  onRemove: (article: Article) => void;
  onReorder: (next: Article[]) => void;
  onClear: () => void;
  onAddLink: (url: string, title?: string) => Promise<void>;
  onCompiled: () => Promise<void>;
};

const SPLIT_KEY = "compile-split";
const PROFILES_KEY = "compile-profiles";
type Split = "combined" | "per_group";

function loadStoredProfiles(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(PROFILES_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((p): p is string => typeof p === "string") : [];
  } catch {
    return [];
  }
}

function statusLabel(d: Digest): string {
  switch (d.status) {
    case "ready":
      return "Ready · EPUB pressed";
    case "failed":
      return "Failed";
    case "generating":
      return "Generating EPUB…";
    default:
      return "Pending";
  }
}

export function DigestQueue({
  queue,
  emailConfigured,
  groupsExist,
  profiles,
  defaultProfile,
  onRemove,
  onReorder,
  onClear,
  onAddLink,
  onCompiled,
}: Props) {
  const toast = useToast();
  const [linkUrl, setLinkUrl] = useState("");
  const [addingLink, setAddingLink] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [digests, setDigests] = useState<Digest[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [compiling, setCompiling] = useState(false);
  const [sendingId, setSendingId] = useState<number | null>(null);
  const [split, setSplit] = useState<Split>(() => {
    if (typeof window === "undefined") return "combined";
    return window.localStorage.getItem(SPLIT_KEY) === "per_group" ? "per_group" : "combined";
  });

  const [selectedProfiles, setSelectedProfiles] = useState<string[]>(loadStoredProfiles);
  // Stored selection filtered to profiles that still exist; never empty while
  // profiles are configured — an empty result falls back to the default.
  const stored = selectedProfiles.filter((p) => profiles.includes(p));
  const activeProfiles =
    stored.length > 0 ? stored : defaultProfile !== null ? [defaultProfile] : [];

  const [optionsOpen, setOptionsOpen] = useState(false);

  const chooseSplit = (next: Split) => {
    setSplit(next);
    window.localStorage.setItem(SPLIT_KEY, next);
  };

  const toggleProfile = (name: string) => {
    const next = activeProfiles.includes(name)
      ? activeProfiles.filter((p) => p !== name)
      : [...activeProfiles, name];
    if (next.length === 0) return; // an edition always targets some profile
    setSelectedProfiles(next);
    window.localStorage.setItem(PROFILES_KEY, JSON.stringify(next));
  };

  const compile = async () => {
    if (queue.length === 0) return;
    setCompiling(true);
    setError(null);
    try {
      let current = await api.createDigest({
        split: groupsExist ? split : "combined",
        profiles: activeProfiles,
      });
      setDigests(current);
      while (current.some((d) => d.status === "pending" || d.status === "generating")) {
        await new Promise((r) => setTimeout(r, 1000));
        current = await Promise.all(
          current.map((d) =>
            d.status === "pending" || d.status === "generating"
              ? api.getDigest(d.id)
              : Promise.resolve(d),
          ),
        );
        setDigests(current);
      }
      const failed = current.filter((d) => d.status === "failed");
      if (failed.length > 0) {
        setError(failed[0].error ?? "digest build failed");
        toast(
          failed.length === current.length
            ? "Edition failed to build"
            : `${failed.length} of ${current.length} editions failed`,
          "error",
        );
      } else if (current.length > 1) {
        toast(`Pressed ${current.length} editions`);
      } else {
        toast(`Edition ${current[0].title} is ready`);
      }
      await onCompiled();
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed");
    } finally {
      setCompiling(false);
    }
  };

  const addLink = async (e: FormEvent) => {
    e.preventDefault();
    const url = linkUrl.trim();
    if (!url || addingLink) return;
    setAddingLink(true);
    try {
      await onAddLink(url);
      setLinkUrl("");
      setLinkOpen(false);
      toast("Link added to queue");
    } catch (err) {
      toast(err instanceof Error ? err.message : "could not add link", "error");
    } finally {
      setAddingLink(false);
    }
  };

  const send = async (digest: Digest) => {
    setSendingId(digest.id);
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
      setSendingId(null);
    }
  };

  const count = queue.length;
  const ready = digests.filter((d) => d.status === "ready");

  return (
    <section className="digest-queue" aria-label="Digest queue">
      <div className="section-head">
        <span className="eyebrow eyebrow-ink">Dispatch / Digest</span>
      </div>

      <div className="queue-readout">
        <span className={`queue-count ${count > 0 ? "armed" : ""}`}>{pad2(count)}</span>
        <div className="queue-count-sub">
          <span className="queue-count-label">Queued</span>
          <span className="queue-count-hint">
            {count === 1 ? "article" : "articles"} · saved on the server
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
              <span className="q-tools">
                <span className="q-reorder">
                  <button
                    type="button"
                    className="feed-tool"
                    aria-label={`Move ${a.title} up in the queue`}
                    disabled={i === 0 || compiling}
                    onClick={() => {
                      const next = [...queue];
                      [next[i - 1], next[i]] = [next[i], next[i - 1]];
                      onReorder(next);
                    }}
                  >
                    ▲
                  </button>
                  <button
                    type="button"
                    className="feed-tool"
                    aria-label={`Move ${a.title} down in the queue`}
                    disabled={i === queue.length - 1 || compiling}
                    onClick={() => {
                      const next = [...queue];
                      [next[i], next[i + 1]] = [next[i + 1], next[i]];
                      onReorder(next);
                    }}
                  >
                    ▼
                  </button>
                </span>
                <button
                  type="button"
                  className="feed-tool danger"
                  aria-label={`Remove ${a.title} from queue`}
                  onClick={() => onRemove(a)}
                >
                  ×
                </button>
              </span>
            </li>
          ))}
        </ol>
      )}

      {linkOpen ? (
        <form onSubmit={(e) => void addLink(e)} className="queue-link-form">
          <label className="feed-form-label" htmlFor="queue-link">
            Add a link
          </label>
          <div className="queue-link-row">
            <input
              id="queue-link"
              type="url"
              inputMode="url"
              autoFocus
              placeholder="https://example.com/article"
              value={linkUrl}
              onChange={(e) => setLinkUrl(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape" && !linkUrl.trim()) setLinkOpen(false);
              }}
            />
            <button type="submit" className="btn btn-ghost" disabled={addingLink || !linkUrl.trim()}>
              <span>{addingLink ? "Adding…" : "Queue link"}</span>
              <span className="btn-arrow">＋</span>
            </button>
          </div>
        </form>
      ) : (
        <button type="button" className="btn btn-ghost" onClick={() => setLinkOpen(true)}>
          <span>Add a link</span>
          <span className="btn-arrow">＋</span>
        </button>
      )}

      <div className="queue-actions">
        <button
          type="button"
          className="btn"
          onClick={() => void compile()}
          disabled={count === 0 || compiling}
        >
          <span>
            {compiling
              ? "Compiling…"
              : activeProfiles.length > 1
                ? `Compile · ${activeProfiles.length} profiles`
                : activeProfiles.length === 1
                  ? `Compile · ${activeProfiles[0]}`
                  : "Compile edition"}
          </span>
          <span className="btn-arrow">→</span>
        </button>

        {count > 0 && !compiling && (
          <button type="button" className="btn btn-ghost" onClick={onClear}>
            <span>Clear queue</span>
            <span className="btn-arrow">×</span>
          </button>
        )}
      </div>

      {(profiles.length > 0 || groupsExist) && (
        <div className="compile-options">
          <button
            type="button"
            className="compile-options-toggle"
            aria-expanded={optionsOpen}
            onClick={() => setOptionsOpen((v) => !v)}
          >
            <span>{optionsOpen ? "▾" : "▸"} Compilation options</span>
            <span className="compile-options-summary">
              {[
                activeProfiles.length > 1 ? `${activeProfiles.length} profiles` : null,
                groupsExist && split === "per_group" ? "one per group" : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </button>

          {optionsOpen && (
            <div className="compile-options-body">
              {profiles.length > 0 && (
                <div>
                  <span className="feed-form-label">Press for</span>
                  <div className="segmented" role="group" aria-label="Device profiles">
                    {profiles.map((name) => (
                      <button
                        key={name}
                        type="button"
                        role="checkbox"
                        aria-checked={activeProfiles.includes(name)}
                        className={`segmented-option ${
                          activeProfiles.includes(name) ? "active" : ""
                        }`}
                        onClick={() => toggleProfile(name)}
                      >
                        {name}
                      </button>
                    ))}
                  </div>
                  <p className="settings-hint">
                    One edition per ticked profile. {defaultProfile ?? ""} is your default.
                  </p>
                </div>
              )}

              {groupsExist && (
                <div>
                  <span className="feed-form-label">Edition mode</span>
                  <div className="segmented" role="radiogroup" aria-label="Edition mode">
                    {(
                      [
                        ["combined", "Combined"],
                        ["per_group", "One per group"],
                      ] as [Split, string][]
                    ).map(([value, label]) => (
                      <button
                        key={value}
                        type="button"
                        role="radio"
                        aria-checked={split === value}
                        className={`segmented-option ${split === value ? "active" : ""}`}
                        onClick={() => chooseSplit(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <p className="settings-hint">
                    Combined = one book, contents sectioned by group. One per group = a separate
                    book per feed group.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {digests.map((d) => (
        <div
          key={d.id}
          className={`queue-status ${
            d.status === "generating" || d.status === "pending"
              ? "generating"
              : d.status === "ready"
                ? "ready"
                : "failed"
          }`}
        >
          <div className="queue-status-row">
            <span>{statusLabel(d)}</span>
          </div>
          <span className="queue-status-ref">
            Ref&nbsp;#{String(d.id).padStart(4, "0")} · {d.title}
          </span>
          {d.status === "ready" && (
            <Link href={`/editions?open=${d.id}`} className="queue-view-link">
              <span>View edition</span>
              <span className="btn-arrow">→</span>
            </Link>
          )}
        </div>
      ))}

      {error && <p className="article-body-error">⚠ {error}</p>}

      {ready.map((d) => (
        <div key={d.id} className="queue-ready-actions">
          <a href={api.downloadDigestUrl(d.id)} className="queue-download" download>
            <span>Download · {d.title}.epub</span>
            <span className="queue-download-arrow">↓</span>
          </a>
          {emailConfigured && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => void send(d)}
              disabled={sendingId === d.id}
            >
              <span>{sendingId === d.id ? "Sending…" : "Send to e-reader"}</span>
              <span className="btn-arrow">✉</span>
            </button>
          )}
        </div>
      ))}
    </section>
  );
}
