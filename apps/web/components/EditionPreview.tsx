"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type ArticleDetail, type DigestArticleEntry } from "../lib/api";
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

function ArticleBody({ articleId, hasFull }: { articleId: number; hasFull: boolean }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<ArticleDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const toggle = async () => {
    const willOpen = !open;
    setOpen(willOpen);
    if (willOpen && !detail) {
      setLoading(true);
      try {
        setDetail(await api.getArticle(articleId));
      } catch {
        // leave detail null; the placeholder copy covers it
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <>
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => void toggle()}>
        <span>{open ? "Hide" : "Preview"}</span>
        <span className="btn-arrow">{open ? "↑" : "↓"}</span>
      </button>
      {open && (
        <div className="article-body">
          {loading && <p className="article-body-loading">Loading content</p>}
          {detail &&
            (detail.full_content ? (
              // full_content is sanitized server-side (nh3 allowlist)
              <div
                className="article-body-content prose"
                dangerouslySetInnerHTML={{ __html: detail.full_content }}
              />
            ) : (
              <div className="article-body-content plain">
                {!hasFull ? "(no full content — the edition uses the summary)" : "(no content)"}
              </div>
            ))}
        </div>
      )}
    </>
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
  const [removing, setRemoving] = useState<Set<number>>(new Set());

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

  const remove = async (ids: number[], label: string) => {
    setRemoving((prev) => new Set([...prev, ...ids]));
    try {
      // Each removal rebuilds the EPUB; do them in series so the final rebuild wins.
      for (const id of ids) await api.removeDigestArticle(digestId, id);
      notify(`Removed ${label} — rebuilding edition`);
      await load();
      onChanged();
    } catch (e) {
      notify(e instanceof Error ? e.message : "remove failed", "error");
    } finally {
      setRemoving((prev) => {
        const next = new Set(prev);
        ids.forEach((id) => next.delete(id));
        return next;
      });
    }
  };

  if (entries === null) return <p className="edition-preview-loading">Loading contents…</p>;
  if (entries.length === 0) return <p className="edition-preview-loading">No articles.</p>;

  const fetched = entries.filter((e) => e.fetch_status === "full").length;
  const failed = entries.filter((e) => e.fetch_status !== null && e.fetch_status !== "full");

  // Sections in first-appearance (position) order.
  const sections: { name: string; items: DigestArticleEntry[] }[] = [];
  for (const e of entries) {
    const name = sectionOf(e);
    let section = sections.find((s) => s.name === name);
    if (!section) {
      section = { name, items: [] };
      sections.push(section);
    }
    section.items.push(e);
  }

  return (
    <div className="edition-preview">
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
                  <span className="muted">({e.fetch_status === "empty" ? "no content" : "summary only"})</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>

      {sections.map((section) => (
        <section key={section.name} className="edition-preview-section">
          <div className="edition-preview-section-head">
            <span className="eyebrow">{section.name}</span>
            <button
              type="button"
              className="btn btn-ghost btn-sm danger"
              disabled={section.items.some((e) => removing.has(e.article_id))}
              onClick={() =>
                void remove(
                  section.items.map((e) => e.article_id),
                  `section “${section.name}”`,
                )
              }
            >
              <span>Remove section</span>
              <span className="btn-arrow">×</span>
            </button>
          </div>
          <ul className="edition-preview-articles">
            {section.items.map((e) => (
              <li key={e.article_id} className="edition-preview-article">
                <div className="edition-preview-article-head">
                  <span className="edition-preview-article-title">{e.title}</span>
                  <span className="article-status">
                    <span className={`status-square ${e.fetch_status === "full" ? "filled" : ""}`} />
                    {e.fetch_status ? FETCH_STATUS_LABEL[e.fetch_status] : "—"}
                  </span>
                  <ArticleBody articleId={e.article_id} hasFull={e.has_full_content} />
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm danger"
                    disabled={removing.has(e.article_id)}
                    onClick={() => void remove([e.article_id], `“${e.title}”`)}
                  >
                    <span>Remove</span>
                    <span className="btn-arrow">×</span>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
