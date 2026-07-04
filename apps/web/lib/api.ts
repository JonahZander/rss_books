// Same-origin by default: production serves the static app from the API
// process; `next dev` proxies /api, /opds and /health via rewrites.
const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export type Feed = {
  id: number;
  url: string;
  title: string;
  site_url: string | null;
  last_polled: string | null;
  created_at: string;
  poll_interval_minutes: number;
  last_error: string | null;
  last_error_at: string | null;
  consecutive_failures: number;
  unread_count: number;
  group_id: number | null;
};

export type Group = {
  id: number;
  name: string;
  position: number;
};

export type Article = {
  id: number;
  feed_id: number;
  title: string;
  url: string;
  summary: string | null;
  published_at: string | null;
  read_at: string | null;
  has_full_content: boolean;
  /** Server-computed lifecycle: new → seen → queued → in_edition (terminal). */
  state: "new" | "seen" | "queued" | "in_edition";
};

export type ArticleDetail = Article & { full_content: string | null };

export type Delivery = {
  id: number;
  digest_id: number;
  channel: string;
  target: string | null;
  status: "sent" | "failed";
  error: string | null;
  created_at: string;
};

export type RenderProfile = {
  name: string;
  link_qr: "off" | "articles" | "all";
  /** "image" pre-renders sizeable tables to PNGs, auto-rotated/split to the screen. */
  table_mode: "native" | "image";
  /** "br" bakes code-block lines in as <br/>; "image" rasterizes each block to PNG. */
  code_mode: "native" | "br" | "image";
  /** Device screen in px; enables screen-fitted table/code images and photo downscaling. */
  screen_width: number | null;
  screen_height: number | null;
};

export type Digest = {
  id: number;
  title: string;
  status: "pending" | "generating" | "ready" | "failed";
  group_name: string | null;
  /** Render-profile name snapshotted at press time; null = legacy settings. */
  profile: string | null;
  epub_path: string | null;
  error: string | null;
  size_bytes: number | null;
  delivered_at: string | null;
  created_at: string;
  article_count: number;
  deliveries: Delivery[];
};

export type DigestArticleEntry = {
  article_id: number;
  position: number;
  title: string;
  url: string;
  source: string;
  group_name: string | null;
  has_full_content: boolean;
  /** Compile-time retrieval outcome; null until the edition was generated. */
  fetch_status: "full" | "summary" | "empty" | null;
};

export type AppSettings = {
  smtp_host: string;
  smtp_port: number;
  smtp_security: "starttls" | "ssl" | "none";
  smtp_username: string;
  smtp_password: string;
  smtp_from: string;
  send_to: string[];
  email_on_ready: boolean;
  opds_auth_enabled: boolean;
  opds_username: string;
  opds_password: string;
  poll_enabled: boolean;
  default_poll_minutes: number;
  retention_enabled: boolean;
  retention_days: number;
  mark_read_on_expand: boolean;
  link_qr: "off" | "articles" | "all";
  reader_fallback: "none" | "tavily" | "jina";
  tavily_api_key: string;
  deadline_enabled: boolean;
  deadline_type: "daily" | "weekly";
  deadline_weekday: number;
  deadline_time: string;
  deadline_split: "combined" | "per_group";
  deadline_profiles: string[];
  /** Compile-UI default render profile; "" or a stale name = first profile. */
  default_profile: string;
  profiles: RenderProfile[];
};

export type ArticleQuery = {
  feedId?: number;
  /** a group id, or "none" for articles of ungrouped feeds */
  groupId?: number | "none";
  unread?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
};

// Pull FastAPI's `detail` message out of an error response so the UI can show
// something human ("That feed was already removed") instead of a bare "404".
async function errorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (body?.detail) {
      return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    }
  } catch {
    // no JSON body, fall back to the status code
  }
  return `${res.status}`;
}

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(await errorDetail(res));
  return (await res.json()) as T;
}

// For endpoints that return no body on success (deletes): still surface a
// useful message on failure rather than throwing the numeric status.
async function ensureOk(res: Response): Promise<void> {
  if (!res.ok) throw new Error(await errorDetail(res));
}

function jsonInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "content-type": "application/json" },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  };
}

export const api = {
  // feeds
  listFeeds: () => fetch(`${BASE}/api/feeds`).then((r) => j<Feed[]>(r)),
  addFeed: (url: string, title: string) =>
    fetch(`${BASE}/api/feeds`, jsonInit("POST", { url, title })).then((r) => j<Feed>(r)),
  patchFeed: (
    id: number,
    patch: { title?: string; poll_interval_minutes?: number; group_id?: number | null },
  ) => fetch(`${BASE}/api/feeds/${id}`, jsonInit("PATCH", patch)).then((r) => j<Feed>(r)),

  // groups
  listGroups: () => fetch(`${BASE}/api/groups`).then((r) => j<Group[]>(r)),
  createGroup: (name: string) =>
    fetch(`${BASE}/api/groups`, jsonInit("POST", { name })).then((r) => j<Group>(r)),
  patchGroup: (id: number, patch: { name?: string; position?: number }) =>
    fetch(`${BASE}/api/groups/${id}`, jsonInit("PATCH", patch)).then((r) => j<Group>(r)),
  deleteGroup: (id: number) =>
    fetch(`${BASE}/api/groups/${id}`, { method: "DELETE" }).then(ensureOk),
  deleteFeed: (id: number) =>
    fetch(`${BASE}/api/feeds/${id}`, { method: "DELETE" }).then(ensureOk),
  refreshAll: () =>
    fetch(`${BASE}/api/feeds/refresh`, { method: "POST" }).then((r) =>
      j<{ inserted: number; errors: number }>(r),
    ),
  refreshFeed: (id: number) =>
    fetch(`${BASE}/api/feeds/${id}/refresh`, { method: "POST" }).then((r) =>
      j<{ inserted: number }>(r),
    ),
  importOpml: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`${BASE}/api/feeds/import`, { method: "POST", body: fd }).then((r) =>
      j<{ added: number; skipped: number; regrouped: number }>(r),
    );
  },
  /** JSON feed list: {"group name": ["feed url", …]}; "ungrouped" = no group. */
  importFeedsJson: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`${BASE}/api/feeds/import-json`, { method: "POST", body: fd }).then((r) =>
      j<{ added: number; skipped: number; regrouped: number }>(r),
    );
  },
  exportOpmlUrl: () => `${BASE}/api/feeds/export.opml`,
  exportJsonUrl: () => `${BASE}/api/feeds/export.json`,

  // articles
  listArticles: ({ feedId, groupId, unread, q, limit, offset }: ArticleQuery = {}, signal?: AbortSignal) => {
    const params = new URLSearchParams();
    if (feedId != null) params.set("feed_id", String(feedId));
    if (groupId != null) params.set("group_id", String(groupId === "none" ? 0 : groupId));
    if (unread) params.set("unread", "true");
    if (q) params.set("q", q);
    if (limit != null) params.set("limit", String(limit));
    if (offset != null) params.set("offset", String(offset));
    const qs = params.size > 0 ? `?${params}` : "";
    return fetch(`${BASE}/api/articles${qs}`, { signal }).then((r) => j<Article[]>(r));
  },
  getArticle: (id: number) =>
    fetch(`${BASE}/api/articles/${id}`).then((r) => j<ArticleDetail>(r)),
  fetchArticle: (id: number) =>
    fetch(`${BASE}/api/articles/${id}/fetch`, { method: "POST" }).then((r) =>
      j<ArticleDetail>(r),
    ),
  markRead: (id: number) =>
    fetch(`${BASE}/api/articles/${id}/read`, { method: "POST" }).then((r) => j<Article>(r)),
  markUnread: (id: number) =>
    fetch(`${BASE}/api/articles/${id}/unread`, { method: "POST" }).then((r) => j<Article>(r)),
  /** Bulk-mark unread articles as read, scoped to a feed or group (or
   * everything, unscoped) — never to a search query or "unread only". */
  markAllRead: ({ feedId, groupId }: { feedId?: number; groupId?: number | "none" } = {}) => {
    const params = new URLSearchParams();
    if (feedId != null) params.set("feed_id", String(feedId));
    if (groupId != null) params.set("group_id", String(groupId === "none" ? 0 : groupId));
    const qs = params.size > 0 ? `?${params}` : "";
    return fetch(`${BASE}/api/articles/mark-all-read${qs}`, { method: "POST" }).then((r) =>
      j<{ updated: number }>(r),
    );
  },

  // queue
  getQueue: () => fetch(`${BASE}/api/queue`).then((r) => j<Article[]>(r)),
  addToQueue: (articleId: number) =>
    fetch(`${BASE}/api/queue/${articleId}`, { method: "POST" }).then((r) => j<Article[]>(r)),
  /** Enqueue an arbitrary URL; its body is fetched when the edition compiles. */
  addLinkToQueue: (url: string, title?: string) =>
    fetch(`${BASE}/api/queue/link`, jsonInit("POST", { url, title: title ?? null })).then((r) =>
      j<Article[]>(r),
    ),
  removeFromQueue: (articleId: number) =>
    fetch(`${BASE}/api/queue/${articleId}`, { method: "DELETE" }).then((r) => j<Article[]>(r)),
  replaceQueue: (articleIds: number[]) =>
    fetch(`${BASE}/api/queue`, jsonInit("PUT", { article_ids: articleIds })).then((r) =>
      j<Article[]>(r),
    ),

  // digests
  listDigests: () => fetch(`${BASE}/api/digests`).then((r) => j<Digest[]>(r)),
  /** Creates one edition (combined) or one per feed group (per_group),
   * crossed with one variant per selected render profile. */
  createDigest: (
    opts: {
      articleIds?: number[];
      title?: string;
      split?: "combined" | "per_group";
      profiles?: string[];
    } = {},
  ) =>
    fetch(
      `${BASE}/api/digests`,
      jsonInit("POST", {
        article_ids: opts.articleIds ?? null,
        title: opts.title ?? null,
        split: opts.split ?? "combined",
        profiles: opts.profiles && opts.profiles.length > 0 ? opts.profiles : null,
      }),
    ).then((r) => j<Digest[]>(r)),
  getDigest: (id: number) => fetch(`${BASE}/api/digests/${id}`).then((r) => j<Digest>(r)),
  listDigestArticles: (id: number) =>
    fetch(`${BASE}/api/digests/${id}/articles`).then((r) => j<DigestArticleEntry[]>(r)),
  removeDigestArticle: (digestId: number, articleId: number) =>
    fetch(`${BASE}/api/digests/${digestId}/articles/${articleId}`, { method: "DELETE" }).then(
      (r) => j<Digest>(r),
    ),
  /** Batch-drop several members at once: one rebuild instead of N. */
  removeDigestArticles: (digestId: number, articleIds: number[]) =>
    fetch(
      `${BASE}/api/digests/${digestId}/articles/remove`,
      jsonInit("POST", { article_ids: articleIds }),
    ).then((r) => j<Digest>(r)),
  /** Standalone HTML rendition of the edition (title page, TOC, chapters). */
  digestPreviewUrl: (id: number) => `${BASE}/api/digests/${id}/preview`,
  deleteDigest: (id: number) =>
    fetch(`${BASE}/api/digests/${id}`, { method: "DELETE" }).then(ensureOk),
  sendDigest: (id: number) =>
    fetch(`${BASE}/api/digests/${id}/send`, { method: "POST" }).then((r) => j<Delivery>(r)),
  downloadDigestUrl: (id: number) => `${BASE}/api/digests/${id}/download`,

  // settings
  getSettings: () => fetch(`${BASE}/api/settings`).then((r) => j<AppSettings>(r)),
  putSettings: (settings: AppSettings) =>
    fetch(`${BASE}/api/settings`, jsonInit("PUT", settings)).then((r) => j<AppSettings>(r)),
  testEmail: (to?: string[]) =>
    fetch(`${BASE}/api/settings/test-email`, jsonInit("POST", { to: to ?? null })).then((r) =>
      j<{ sent_to: string[] }>(r),
    ),
};

export function emailConfigured(s: AppSettings): boolean {
  return Boolean(s.smtp_host && s.smtp_from && s.send_to.length > 0);
}

/** The profile the compile UI preselects: the named one if it still exists,
 * else the first profile, else null (no profiles configured). */
export function defaultProfileName(s: AppSettings): string | null {
  const named = s.profiles.find((p) => p.name === s.default_profile);
  return named?.name ?? s.profiles[0]?.name ?? null;
}
