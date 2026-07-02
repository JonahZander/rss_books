"use client";

import type { ArticleDetail } from "../lib/api";
import { hostnameOf } from "../lib/url";
import { Drawer } from "./Drawer";

/** The shared article-reading drawer used by both the triage desk and the
 * edition review: a slide-over with the article body, a source link, and
 * prev/next navigation across the surrounding list. Purely presentational -
 * the parent owns fetching `detail` and the loading flag. */
export function ArticleReaderDrawer({
  eyebrow,
  title,
  url,
  index,
  count,
  onIndex,
  onClose,
  loading,
  detail,
  fallback,
}: {
  eyebrow: string;
  title: string;
  url: string;
  index: number;
  count: number;
  onIndex: (i: number) => void;
  onClose: () => void;
  loading: boolean;
  detail: ArticleDetail | null;
  /** Body shown when there is no full content for the current article. */
  fallback: string;
}) {
  return (
    <Drawer
      open
      eyebrow={eyebrow}
      title={title}
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
            {index + 1} / {count}
          </span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={index === count - 1}
            onClick={() => onIndex(index + 1)}
          >
            <span>Next</span>
            <span className="btn-arrow">→</span>
          </button>
        </div>
      }
    >
      <p className="drawer-source">
        <a href={url} target="_blank" rel="noreferrer">
          Read the original at {hostnameOf(url)} ↗
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
          <div className="article-body-content plain">{fallback}</div>
        ))}
    </Drawer>
  );
}
