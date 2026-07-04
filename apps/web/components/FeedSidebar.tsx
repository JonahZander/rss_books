"use client";

import { useRef, useState } from "react";
import type { Feed, Group } from "../lib/api";
import { api } from "../lib/api";
import { capCount, pad2 } from "../lib/format";
import { hostnameOf } from "../lib/url";
import { useToast } from "./Toasts";

type GroupSelection = number | "none" | null;

type Props = {
  feeds: Feed[];
  groups: Group[];
  selectedFeedId: number | null;
  selectedGroupId: GroupSelection;
  onSelect: (id: number | null) => void;
  onSelectGroup: (id: GroupSelection) => void;
  onAdd: (url: string, title: string) => Promise<void>;
  onDelete: (feed: Feed) => void;
  onDeleteGroup: (group: Group) => void;
  onRefresh: () => Promise<void>;
  onChanged: () => Promise<void>;
};

const COLLAPSE_KEY = "sidebar-collapsed";

function relPoll(iso: string | null): string {
  if (!iso) return "never polled";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  const mins = Math.round((Date.now() - d.getTime()) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function loadCollapsed(): Record<string, boolean> {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(COLLAPSE_KEY) ?? "{}") as Record<
      string,
      boolean
    >;
  } catch {
    return {};
  }
}

export function FeedSidebar({
  feeds,
  groups,
  selectedFeedId,
  selectedGroupId,
  onSelect,
  onSelectGroup,
  onAdd,
  onDelete,
  onDeleteGroup,
  onRefresh,
  onChanged,
}: Props) {
  const toast = useToast();
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [errorOpenId, setErrorOpenId] = useState<number | null>(null);
  const [groupPickId, setGroupPickId] = useState<number | null>(null);
  const [renamingGroupId, setRenamingGroupId] = useState<number | null>(null);
  const [groupRenameValue, setGroupRenameValue] = useState("");
  const [newGroupName, setNewGroupName] = useState("");
  const [addingGroup, setAddingGroup] = useState(false);
  const [addingFeed, setAddingFeed] = useState(false);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(loadCollapsed);
  const fileRef = useRef<HTMLInputElement>(null);

  const grouped = groups.length > 0;
  const ungroupedFeeds = feeds.filter((f) => f.group_id == null);
  const orderedFeeds = grouped
    ? [...groups.flatMap((g) => feeds.filter((f) => f.group_id === g.id)), ...ungroupedFeeds]
    : feeds;
  const indexOf = new Map(orderedFeeds.map((f, i) => [f.id, i]));

  const toggleCollapsed = (key: string) => {
    setCollapsed((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      window.localStorage.setItem(COLLAPSE_KEY, JSON.stringify(next));
      return next;
    });
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url || !title) return;
    setBusy(true);
    try {
      await onAdd(url, title);
      setUrl("");
      setTitle("");
      setAddingFeed(false);
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

  const saveRename = async (feed: Feed) => {
    const next = renameValue.trim();
    setRenamingId(null);
    if (!next || next === feed.title) return;
    try {
      await api.patchFeed(feed.id, { title: next });
      await onChanged();
      toast(`Renamed to “${next}”`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "rename failed", "error");
    }
  };

  const moveToGroup = async (feed: Feed, value: string) => {
    setGroupPickId(null);
    const groupId = value === "" ? null : Number(value);
    if (groupId === feed.group_id) return;
    try {
      await api.patchFeed(feed.id, { group_id: groupId });
      await onChanged();
      const target = groupId === null ? "Ungrouped" : groups.find((g) => g.id === groupId)?.name;
      toast(`“${feed.title}” → ${target ?? "group"}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "move failed", "error");
    }
  };

  const saveGroupRename = async (group: Group) => {
    const next = groupRenameValue.trim();
    setRenamingGroupId(null);
    if (!next || next === group.name) return;
    try {
      await api.patchGroup(group.id, { name: next });
      await onChanged();
      toast(`Group renamed to “${next}”`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "rename failed", "error");
    }
  };

  const createGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newGroupName.trim();
    if (!name) return;
    try {
      await api.createGroup(name);
      setNewGroupName("");
      setAddingGroup(false);
      await onChanged();
      toast(`Group “${name}” created`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "could not add group", "error");
    }
  };

  const refreshOne = async (feed: Feed) => {
    try {
      const r = await api.refreshFeed(feed.id);
      toast(`${feed.title}: ${r.inserted} new`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "refresh failed", "error");
    }
    await onChanged();
  };

  const importFile = async (file: File) => {
    // one Import button for both formats: .json (or a leading "{") → JSON list,
    // anything else → OPML
    const isJson =
      file.name.toLowerCase().endsWith(".json") ||
      (await file.slice(0, 64).text()).trimStart().startsWith("{");
    try {
      const r = isJson ? await api.importFeedsJson(file) : await api.importOpml(file);
      const regrouped = r.regrouped > 0 ? `, ${r.regrouped} regrouped` : "";
      toast(`${isJson ? "JSON" : "OPML"} import: ${r.added} added, ${r.skipped} skipped${regrouped}`);
      await onChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : "import failed", "error");
    }
  };

  const feedRow = (f: Feed) => (
    <>
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
        <span className="feed-row-index">{pad2((indexOf.get(f.id) ?? 0) + 1)}</span>
        {renamingId === f.id ? (
          <input
            className="feed-rename-input"
            value={renameValue}
            autoFocus
            onChange={(e) => setRenameValue(e.target.value)}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === "Enter") void saveRename(f);
              if (e.key === "Escape") setRenamingId(null);
            }}
            onBlur={() => void saveRename(f)}
            aria-label={`Rename ${f.title}`}
          />
        ) : groupPickId === f.id ? (
          <select
            className="feed-rename-input"
            autoFocus
            defaultValue={f.group_id == null ? "" : String(f.group_id)}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => void moveToGroup(f, e.target.value)}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === "Escape") setGroupPickId(null);
            }}
            onBlur={() => setGroupPickId(null)}
            aria-label={`Move ${f.title} to group`}
          >
            <option value="">No group</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        ) : (
          <span>
            <span className="feed-row-title">
              {f.title}
              {f.last_error && (
                <button
                  type="button"
                  className="feed-error-badge"
                  title={f.last_error}
                  aria-label={`${f.title} failed to refresh, show details`}
                  aria-expanded={errorOpenId === f.id}
                  onClick={(e) => {
                    e.stopPropagation();
                    setErrorOpenId(errorOpenId === f.id ? null : f.id);
                  }}
                >
                  ▲
                </button>
              )}
            </span>
            <span className="feed-row-sub">
              {hostnameOf(f.site_url ?? f.url)} · {relPoll(f.last_polled)}
            </span>
          </span>
        )}
        <span className="feed-row-end">
          {f.unread_count > 0 && <span className="unread-badge">{capCount(f.unread_count)}</span>}
          <span className="feed-row-tools">
            <button
              type="button"
              className="feed-tool"
              aria-label={`Refresh ${f.title}`}
              title="Refresh now"
              onClick={(e) => {
                e.stopPropagation();
                void refreshOne(f);
              }}
            >
              ↻
            </button>
            {grouped && (
              <button
                type="button"
                className="feed-tool"
                aria-label={`Move ${f.title} to group`}
                title="Move to group"
                onClick={(e) => {
                  e.stopPropagation();
                  setGroupPickId(f.id);
                }}
              >
                ⊞
              </button>
            )}
            <button
              type="button"
              className="feed-tool"
              aria-label={`Rename ${f.title}`}
              title="Rename"
              onClick={(e) => {
                e.stopPropagation();
                setRenameValue(f.title);
                setRenamingId(f.id);
              }}
            >
              ✎
            </button>
            <button
              type="button"
              className="feed-tool danger"
              aria-label={`Remove ${f.title}`}
              title="Remove"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(f);
              }}
            >
              ×
            </button>
          </span>
        </span>
      </div>
      {errorOpenId === f.id && f.last_error && (
        <div className="feed-error-detail">
          <p>{f.last_error}</p>
          <p className="feed-error-detail-meta">
            {f.consecutive_failures} consecutive failure{f.consecutive_failures === 1 ? "" : "s"}
          </p>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => void refreshOne(f)}
          >
            <span>Retry now</span>
            <span className="btn-arrow">↻</span>
          </button>
        </div>
      )}
    </>
  );

  const groupSection = (key: string, name: string, sectionFeeds: Feed[], group?: Group) => {
    const isCollapsed = collapsed[key] ?? false;
    const unread = sectionFeeds.reduce((n, f) => n + f.unread_count, 0);
    const selected = group ? selectedGroupId === group.id : selectedGroupId === "none";
    return (
      <li key={key} className="group-section">
        <div className={`group-head ${selected ? "active" : ""}`}>
          <button
            type="button"
            className={`group-caret ${isCollapsed ? "closed" : ""}`}
            aria-expanded={!isCollapsed}
            aria-label={`${isCollapsed ? "Expand" : "Collapse"} ${name}`}
            onClick={() => toggleCollapsed(key)}
          >
            ▾
          </button>
          {group && renamingGroupId === group.id ? (
            <input
              className="feed-rename-input"
              value={groupRenameValue}
              autoFocus
              onChange={(e) => setGroupRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void saveGroupRename(group);
                if (e.key === "Escape") setRenamingGroupId(null);
              }}
              onBlur={() => void saveGroupRename(group)}
              aria-label={`Rename group ${name}`}
            />
          ) : (
            <button
              type="button"
              className="group-name"
              onClick={() => onSelectGroup(group ? group.id : "none")}
            >
              {name}
            </button>
          )}
          <span className="feed-row-end">
            {unread > 0 && <span className="unread-badge">{capCount(unread)}</span>}
            {group && (
              <span className="feed-row-tools">
                <button
                  type="button"
                  className="feed-tool"
                  aria-label={`Rename group ${name}`}
                  title="Rename group"
                  onClick={() => {
                    setGroupRenameValue(name);
                    setRenamingGroupId(group.id);
                  }}
                >
                  ✎
                </button>
                <button
                  type="button"
                  className="feed-tool danger"
                  aria-label={`Delete group ${name}`}
                  title="Delete group (feeds stay)"
                  onClick={() => onDeleteGroup(group)}
                >
                  ×
                </button>
              </span>
            )}
          </span>
        </div>
        <div className={`group-body ${isCollapsed ? "collapsed" : ""}`}>
          <ul className="feed-list group-feeds">
            {sectionFeeds.map((f) => (
              <li key={f.id}>{feedRow(f)}</li>
            ))}
          </ul>
        </div>
      </li>
    );
  };

  return (
    <aside className="feed-sidebar" aria-label="Feeds">
      <div className="section-head">
        <span className="eyebrow eyebrow-ink">Index / Feeds</span>
        <span className="counter">{pad2(feeds.length)}</span>
      </div>

      <ul className="feed-list">
        <li>
          <button
            type="button"
            className={`feed-row all ${
              selectedFeedId === null && selectedGroupId === null ? "active" : ""
            }`}
            onClick={() => {
              onSelect(null);
              onSelectGroup(null);
            }}
          >
            <span className="feed-row-index">★</span>
            <span>
              <span className="feed-row-title">All dispatches</span>
              <span className="feed-row-sub">Unified stream · All feeds</span>
            </span>
          </button>
        </li>
        {grouped ? (
          <>
            {groups.map((g) =>
              groupSection(
                String(g.id),
                g.name,
                feeds.filter((f) => f.group_id === g.id),
                g,
              ),
            )}
            {ungroupedFeeds.length > 0 && groupSection("none", "Ungrouped", ungroupedFeeds)}
          </>
        ) : (
          feeds.map((f) => <li key={f.id}>{feedRow(f)}</li>)
        )}
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

      {addingFeed ? (
        <form onSubmit={submit} className="feed-form">
          <span className="eyebrow eyebrow-ink">Add a feed</span>
          <div>
            <label className="feed-form-label" htmlFor="feed-url">
              URL
            </label>
            <input
              id="feed-url"
              placeholder="https://example.com/feed.xml"
              value={url}
              autoFocus
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") setAddingFeed(false);
              }}
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
              onKeyDown={(e) => {
                if (e.key === "Escape") setAddingFeed(false);
              }}
              required
            />
          </div>
          <button type="submit" className="btn" disabled={busy}>
            <span>{busy ? "Adding…" : "Add feed"}</span>
            <span className="btn-arrow">→</span>
          </button>
        </form>
      ) : (
        <button type="button" className="btn btn-ghost" onClick={() => setAddingFeed(true)}>
          <span>Add feed</span>
          <span className="btn-arrow">＋</span>
        </button>
      )}

      {addingGroup ? (
        <form onSubmit={createGroup} className="group-form">
          <input
            placeholder="New group name"
            value={newGroupName}
            autoFocus
            onChange={(e) => setNewGroupName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setNewGroupName("");
                setAddingGroup(false);
              }
            }}
            onBlur={() => {
              if (!newGroupName.trim()) setAddingGroup(false);
            }}
            aria-label="New group name"
          />
          <button type="submit" className="btn btn-ghost">
            <span>Create</span>
            <span className="btn-arrow">→</span>
          </button>
        </form>
      ) : (
        <button type="button" className="btn btn-ghost" onClick={() => setAddingGroup(true)}>
          <span>Add group</span>
          <span className="btn-arrow">＋</span>
        </button>
      )}

      <div className="opml-row">
        <input
          ref={fileRef}
          type="file"
          accept=".opml,.xml,.json,text/xml,application/json"
          className="visually-hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void importFile(file);
            e.target.value = "";
          }}
        />
        <button type="button" className="btn btn-ghost" onClick={() => fileRef.current?.click()}>
          <span>Import OPML / JSON</span>
          <span className="btn-arrow">↑</span>
        </button>
        <a className="btn btn-ghost" href={api.exportOpmlUrl()} download>
          <span>Export OPML</span>
          <span className="btn-arrow">↓</span>
        </a>
        <a className="btn btn-ghost" href={api.exportJsonUrl()} download>
          <span>Export JSON</span>
          <span className="btn-arrow">↓</span>
        </a>
      </div>
    </aside>
  );
}
