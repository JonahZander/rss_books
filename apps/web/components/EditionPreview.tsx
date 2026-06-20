"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type ArticleDetail, type DigestArticleEntry } from "../lib/api";
import { ConfirmDialog } from "./ConfirmDialog";
import { Drawer } from "./Drawer";
import { hostnameOf } from "../lib/url";

/** group_name when present, else the feed title — the section an article sits in. */
function sectionOf(entry: DigestArticleEntry): string {
  return entry.group_name ?? entry.source;
}

const FETCH_STATUS_LABEL: Record<NonNullable<DigestArticleEntry["fetch_status"]>, string> = {
  full: "Full",
  summary: "Summary",
  empty: "Empty",
};

/** The article-reading drawer: one member's body, with prev/next across the
 * whole edition so you can read through without collapsing back to the list. */
function ReadDrawer({
  entries,
  index,
  onIndex,
  onClose,
}: {
  entries: DigestArticleEntry[];
  index: number;
  onIndex: (i: number) => void;
  onClose: () => void;
}) {
  const entry = entries[index];
  const [detail, setDetail] = useState<ArticleDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let live = true;
    // Reset + load whenever the shown article changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDetail(null);
    setLoading(true);
    api
      .getArticle(entry.article_id)
      .then((d) => live && setDetail(d))
      .catch(() => live && setDetail(null))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [entry.article_id]);

  const status = entry.fetch_status ? FETCH_STATUS_LABEL[entry.fetch_status] : "—";

  return (
    <Drawer
      open
      eyebrow={`${sectionOf(entry)} · ${status} in this edition`}
      title={entry.title}
      onClose={onClose}
      footer={
        <div className="drawer-nav">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={index === 0}
            onClick={() => onIndex(index - 1)}
          >
            <span className="btn-arrow">←</span>
            <span>Previous</span>
          </button>
          <span className="drawer-nav-pos">
            {index + 1} / {entries.length}
          </span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={index === entries.length - 1}
            onClick={() => onIndex(index + 1)}
          >
            <span>Next</span>
            <span className="btn-arrow">→</span>
          </button>
        </div>
      }
    >
      <p className="drawer-source">
        <a href={entry.url} target="_blank" rel="noreferrer">
          Read the original at {hostnameOf(entry.url)} ↗
        </a>
      </p>
      {loading && <p className="article-body-loading">Loading content</p>}
      {!loading &&
        (detail?.full_content ? (
          // full_content is sanitized server-side (nh3 allowlist)
          <div
            className="article-body-content prose"
            dangerouslySetInnerHTML={{ __html: detail.full_content }}
          />
        ) : (
          <div className="article-body-content plain">
            {entry.fetch_status === "full"
              ? "(no stored content)"
              : "This edition uses the feed summary — the full text could not be fetched."}
          </div>
        ))}
    </Drawer>
  );
}

export function EditionPreview({
  digestId,
  onChanged,
  notify,
}: {
  digestId: number;
  /** Called after a removal so the parent can refresh the edition list. */
  onChanged: () => void;
  notify: (msg: string, kind?: "info" | "error") => void;
}) {
  const [entries, setEntries] = useState<DigestArticleEntry[] | null>(null);
  const [marked, setMarked] = useState<Set<number>>(new Set());
  const [applying, setApplying] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [readIndex, setReadIndex] = useState<number | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      setEntries(await api.listDigestArticles(digestId));
    } catch (e) {
      notify(e instanceof Error ? e.message : "could not load edition contents", "error");
    }
  }, [digestId, notify]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const toggle = (id: number) =>
    setMarked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const toggleSection = (ids: number[]) =>
    setMarked((prev) => {
      const next = new Set(prev);
      const allMarked = ids.every((id) => next.has(id));
      ids.forEach((id) => (allMarked ? next.delete(id) : next.add(id)));
      return next;
    });

  const applyRemovals = async () => {
    setConfirmOpen(false);
    const ids = [...marked];
    setApplying(true);
    try {
      await api.removeDigestArticles(digestId, ids);
      notify(`Removed ${ids.length} ${ids.length === 1 ? "article" : "articles"} — rebuilding edition`);
      setMarked(new Set());
      await load();
      onChanged();
    } catch (e) {
      notify(e instanceof Error ? e.message : "remove failed", "error");
    } finally {
      setApplying(false);
    }
  };

  // Sections in first-appearance (position) order — mirrors the EPUB TOC.
  const sections = useMemo(() => {
    const out: { name: string; items: DigestArticleEntry[] }[] = [];
    for (const e of entries ?? []) {
      const name = sectionOf(e);
      let section = out.find((s) => s.name === name);
      if (!section) {
        section = { name, items: [] };
        out.push(section);
      }
      section.items.push(e);
    }
    return out;
  }, [entries]);

  if (entries === null) return <p className="edition-preview-loading">Loading contents…</p>;
  if (entries.length === 0) return <p className="edition-preview-loading">No articles.</p>;

  const fetched = entries.filter((e) => e.fetch_status === "full").length;
  const failed = entries.filter((e) => e.fetch_status !== null && e.fetch_status !== "full");
  const removingAll = marked.size === entries.length;

  return (
    <div className="edition-preview">
      <div className="edition-preview-bar">
        <div className="edition-preview-summary">
          <span className="stamp">
            {fetched} of {entries.length} links fetched
          </span>
          {failed.length > 0 && (
            <details className="edition-preview-failed">
              <summary>{failed.length} could not be fetched</summary>
              <ul>
                {failed.map((e) => (
                  <li key={e.article_id}>
                    <a href={e.url} target="_blank" rel="noreferrer">
                      {hostnameOf(e.url)} ↗
                    </a>{" "}
                    — {e.title}{" "}
                    <span className="muted">
                      ({e.fetch_status === "empty" ? "no content" : "summary only"})
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => setPreviewOpen(true)}
        >
          <span>Preview edition</span>
          <span className="btn-arrow">⤢</span>
        </button>
      </div>

      <p className="edition-preview-legend">
        <span className="legend-item">
          <span className="status-square filled" /> Full — whole article
        </span>
        <span className="legend-item">
          <span className="status-square" /> Summary / Empty — feed excerpt or nothing fetched
        </span>
      </p>

      {sections.map((section) => {
        const ids = section.items.map((e) => e.article_id);
        const allMarked = ids.every((id) => marked.has(id));
        return (
          <section key={section.name} className="edition-preview-section">
            <div className="edition-preview-section-head">
              <span className="eyebrow">{section.name}</span>
              <button
                type="button"
                className="btn btn-ghost btn-sm danger"
                onClick={() => toggleSection(ids)}
              >
                <span>{allMarked ? "Keep section" : "Remove section"}</span>
                <span className="btn-arrow">{allMarked ? "↺" : "×"}</span>
              </button>
            </div>
            <ul className="edition-preview-articles">
              {section.items.map((e) => {
                const idx = entries.indexOf(e);
                const isMarked = marked.has(e.article_id);
                return (
                  <li
                    key={e.article_id}
                    className={`edition-preview-article${isMarked ? " marked" : ""}`}
                  >
                    <span className="edition-preview-article-title">{e.title}</span>
                    <span className="article-status">
                      <span
                        className={`status-square ${e.fetch_status === "full" ? "filled" : ""}`}
                      />
                      {e.fetch_status ? FETCH_STATUS_LABEL[e.fetch_status] : "—"}
                    </span>
                    <div className="edition-preview-article-actions">
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => setReadIndex(idx)}
                      >
                        <span>Read</span>
                        <span className="btn-arrow">↗</span>
                      </button>
                      <button
                        type="button"
                        className={`btn btn-ghost btn-sm ${isMarked ? "" : "danger"}`}
                        onClick={() => toggle(e.article_id)}
                      >
                        <span>{isMarked ? "Keep" : "Remove"}</span>
                        <span className="btn-arrow">{isMarked ? "↺" : "×"}</span>
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}

      {marked.size > 0 && (
        <div className="edition-preview-apply" role="region" aria-label="Pending removals">
          <span className="stamp">
            {marked.size} marked for removal
            {removingAll && " — this empties the edition"}
          </span>
          <div className="edition-preview-apply-actions">
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setMarked(new Set())}
            >
              <span>Clear</span>
            </button>
            <button
              type="button"
              className="btn btn-danger btn-sm"
              disabled={applying}
              onClick={() => setConfirmOpen(true)}
            >
              <span>{applying ? "Removing…" : `Apply removals (${marked.size})`}</span>
              <span className="btn-arrow">→</span>
            </button>
          </div>
        </div>
      )}

      {readIndex !== null && (
        <ReadDrawer
          entries={entries}
          index={readIndex}
          onIndex={setReadIndex}
          onClose={() => setReadIndex(null)}
        />
      )}

      {previewOpen && (
        <Drawer
          open
          eyebrow="As it lands on your device"
          title="Edition preview"
          onClose={() => setPreviewOpen(false)}
        >
          <iframe
            className="preview-frame"
            src={api.digestPreviewUrl(digestId)}
            sandbox="allow-same-origin"
            title="Edition preview"
          />
        </Drawer>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title={`Remove ${marked.size} ${marked.size === 1 ? "article" : "articles"} from this edition?`}
        body={
          removingAll
            ? "This removes every article — the edition will be left empty until you compile a new one. Articles stay in your library."
            : "The edition's EPUB will rebuild without them. Articles stay in your library."
        }
        confirmLabel="Remove & rebuild"
        onConfirm={() => void applyRemovals()}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
