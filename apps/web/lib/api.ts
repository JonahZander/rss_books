const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8765";

export type Feed = {
  id: number;
  url: string;
  title: string;
  site_url: string | null;
  last_polled: string | null;
  created_at: string;
};

export type Article = {
  id: number;
  feed_id: number;
  title: string;
  url: string;
  summary: string | null;
  published_at: string | null;
  has_full_content: boolean;
};

export type ArticleDetail = Article & { full_content: string | null };

export type Digest = {
  id: number;
  title: string;
  status: "pending" | "generating" | "ready";
  epub_path: string | null;
  created_at: string;
};

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return (await res.json()) as T;
}

export const api = {
  listFeeds: () => fetch(`${BASE}/api/feeds`).then((r) => j<Feed[]>(r)),
  addFeed: (url: string, title: string) =>
    fetch(`${BASE}/api/feeds`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url, title }),
    }).then((r) => j<Feed>(r)),
  deleteFeed: (id: number) =>
    fetch(`${BASE}/api/feeds/${id}`, { method: "DELETE" }).then((r) => {
      if (!r.ok) throw new Error(`${r.status}`);
    }),
  refreshAll: () =>
    fetch(`${BASE}/api/feeds/refresh`, { method: "POST" }).then((r) =>
      j<{ inserted: number }>(r),
    ),
  listArticles: (feedId?: number) => {
    const qs = feedId != null ? `?feed_id=${feedId}` : "";
    return fetch(`${BASE}/api/articles${qs}`).then((r) => j<Article[]>(r));
  },
  getArticle: (id: number) =>
    fetch(`${BASE}/api/articles/${id}`).then((r) => j<ArticleDetail>(r)),
  fetchArticle: (id: number) =>
    fetch(`${BASE}/api/articles/${id}/fetch`, { method: "POST" }).then((r) =>
      j<ArticleDetail>(r),
    ),
  createDigest: (articleIds: number[], title?: string) =>
    fetch(`${BASE}/api/digests`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ article_ids: articleIds, title }),
    }).then((r) => j<Digest>(r)),
  getDigest: (id: number) => fetch(`${BASE}/api/digests/${id}`).then((r) => j<Digest>(r)),
  downloadDigestUrl: (id: number) => `${BASE}/api/digests/${id}/download`,
};
