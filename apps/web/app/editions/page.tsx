"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { EditionPreview } from "../../components/EditionPreview";
import { Masthead } from "../../components/Masthead";
import { useToast } from "../../components/Toasts";
import { api, defaultProfileName, emailConfigured, type AppSettings, type Digest } from "../../lib/api";
import { fmtDate, fmtSize } from "../../lib/format";

const STATUS_LABEL: Record<Digest["status"], string> = {
  pending: "Pending",
  generating: "Generating",
  ready: "Ready",
  failed: "Failed",
};

/** Static export requires useSearchParams to sit under a Suspense boundary
 * (a next build failure otherwise); this wrapper is the whole reason the
 * page body is split into a separate component below. */
export default function Editions() {
  return (
    <Suspense fallback={<Masthead />}>
      <EditionsInner />
    </Suspense>
  );
}

function EditionsInner() {
  const toast = useToast();
  const searchParams = useSearchParams();
  const openParam = searchParams.get("open");
  const [digests, setDigests] = useState<Digest[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Digest | null>(null);
  const [sendingId, setSendingId] = useState<number | null>(null);
  const [previewId, setPreviewId] = useState<number | null>(null);
  const [recompileFor, setRecompileFor] = useState<number | null>(null);
  const [recompileProfiles, setRecompileProfiles] = useState<string[]>([]);
  const [recompileSplit, setRecompileSplit] = useState<"combined" | "per_group">("combined");
  const [recompiling, setRecompiling] = useState(false);
  const [groupsExist, setGroupsExist] = useState(false);

  const refresh = useCallback(async () => {
    setDigests(await api.listDigests());
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
    api.getSettings().then(setSettings, () => {});
    api.listGroups().then((groups) => setGroupsExist(groups.length > 0), () => {});
  }, [refresh]);

  const busy = digests.some((d) => d.status === "pending" || d.status === "generating");
  useEffect(() => {
    if (!busy) return;
    const id = window.setInterval(() => void refresh(), 1500);
    return () => window.clearInterval(id);
  }, [busy, refresh]);

  // Coming from "View edition →" on the triage desk (?open=<id>): expand that
  // edition's review panel and scroll it into view, once per param value so
  // re-renders (or the busy-poll refresh above) don't keep re-triggering it.
  const openedParam = useRef<string | null>(null);
  useEffect(() => {
    if (!openParam || openedParam.current === openParam) return;
    const id = Number(openParam);
    const found = Number.isFinite(id) && digests.some((d) => d.id === id);
    if (!found) {
      // Once the list has loaded at least once, a missing id is permanent —
      // stop rescanning on every busy-poll refresh above.
      if (digests.length > 0) openedParam.current = openParam;
      return;
    }
    openedParam.current = openParam;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPreviewId(id);
    requestAnimationFrame(() => {
      document
        .querySelector(`[data-digest-id="${id}"]`)
        ?.scrollIntoView({ block: "center", behavior: "smooth" });
    });
  }, [openParam, digests]);

  const send = async (digest: Digest) => {
    setSendingId(digest.id);
    try {
      const delivery = await api.sendDigest(digest.id);
      if (delivery.status === "sent") {
        toast(`Edition ${digest.title} emailed to ${delivery.target}`);
      } else {
        toast(delivery.error ?? "send failed", "error");
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : "send failed", "error");
    } finally {
      setSendingId(null);
      await refresh();
    }
  };

  const openRecompile = (digest: Digest) => {
    // Preselect the profile the edition was pressed with, else the default.
    const initial = digest.profile ?? (settings ? defaultProfileName(settings) : null);
    setRecompileProfiles(initial ? [initial] : []);
    setRecompileSplit("combined");
    setRecompileFor(recompileFor === digest.id ? null : digest.id);
  };

  const toggleRecompileProfile = (name: string) => {
    setRecompileProfiles((prev) =>
      prev.includes(name) ? prev.filter((p) => p !== name) : [...prev, name],
    );
  };

  const recompile = async (digest: Digest) => {
    const profiles = recompileProfiles;
    const split = recompileSplit;
    setRecompileFor(null);
    setRecompiling(true);
    try {
      const members = await api.listDigestArticles(digest.id);
      if (members.length === 0) {
        toast("Edition has no articles left to press", "error");
        return;
      }
      await api.createDigest({
        articleIds: members.map((m) => m.article_id),
        split,
        profiles: profiles.length > 0 ? profiles : undefined,
      });
      toast(`Pressing a new edition from ${digest.title}…`);
      await refresh();
    } catch (e) {
      toast(e instanceof Error ? e.message : "recompile failed", "error");
    } finally {
      setRecompiling(false);
    }
  };

  const remove = async () => {
    if (!deleteTarget) return;
    const digest = deleteTarget;
    setDeleteTarget(null);
    try {
      await api.deleteDigest(digest.id);
      toast(`Edition ${digest.title} deleted`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "delete failed", "error");
    }
    await refresh();
  };

  const canEmail = settings ? emailConfigured(settings) : false;

  return (
    <div className="app">
      <Masthead />
      <main className="page-main" aria-label="Editions">
        <div className="content-head">
          <div>
            <span className="eyebrow">Pressed editions</span>
            <h2 className="content-title">Editions</h2>
          </div>
          <div className="content-meta">
            <span>
              Total <strong>{String(digests.length).padStart(2, "0")}</strong>
            </span>
          </div>
        </div>

        {digests.length === 0 ? (
          <p className="empty-state">
            No editions pressed yet
            <small>Queue articles on the triage desk and compile.</small>
          </p>
        ) : (
          <ul className="edition-list">
            {digests.map((d) => (
              <li key={d.id} className={`edition-row status-${d.status}`} data-digest-id={d.id}>
                <div className="edition-main">
                  <span className="edition-ref">#{String(d.id).padStart(4, "0")}</span>
                  <div className="edition-titleblock">
                    <span className="edition-title">{d.title}</span>
                    <span className="edition-sub">
                      {fmtDate(d.created_at)} · {d.article_count}{" "}
                      {d.article_count === 1 ? "article" : "articles"} · {fmtSize(d.size_bytes)}
                    </span>
                    {d.status === "failed" && d.error && (
                      <span className="edition-error">⚠ {d.error}</span>
                    )}
                    {d.deliveries.length > 0 && (
                      <span className="edition-deliveries">
                        {d.deliveries[0].status === "sent" ? "✓ emailed" : "✗ email failed"} ·{" "}
                        {fmtDate(d.deliveries[0].created_at)}
                        {d.deliveries[0].status === "failed" && d.deliveries[0].error
                          ? ` - ${d.deliveries[0].error}`
                          : ""}
                      </span>
                    )}
                  </div>
                  <span className="edition-chips">
                    {d.profile && (
                      <span
                        className="edition-chip"
                        title={`Rendered with the “${d.profile}” device profile`}
                      >
                        {d.profile}
                      </span>
                    )}
                    <span
                      className="edition-chip"
                      title={
                        d.group_name
                          ? `Contains only articles from the “${d.group_name}” feed group`
                          : "One book with everything that was queued; contents sectioned by feed group"
                      }
                    >
                      {d.group_name ? `Group · ${d.group_name}` : "Combined"}
                    </span>
                    {d.status !== "ready" && (
                      <span className={`status-chip chip-${d.status}`}>
                        {STATUS_LABEL[d.status]}
                      </span>
                    )}
                  </span>
                </div>
                <div className="edition-actions">
                  <button
                    type="button"
                    className="btn btn-outline btn-sm"
                    aria-expanded={previewId === d.id}
                    onClick={() => setPreviewId(previewId === d.id ? null : d.id)}
                  >
                    <span>{previewId === d.id ? "Hide" : "Review"}</span>
                    <span className="btn-arrow">{previewId === d.id ? "↑" : "↓"}</span>
                  </button>
                  {d.status === "ready" && (
                    <a className="btn btn-sm" href={api.downloadDigestUrl(d.id)} download>
                      <span>Download</span>
                      <span className="btn-arrow">↓</span>
                    </a>
                  )}
                  <span className="edition-tools">
                    {d.status === "ready" &&
                      (canEmail ? (
                        <button
                          type="button"
                          className="feed-tool"
                          title="Send to e-reader"
                          aria-label={`Send ${d.title} to e-reader`}
                          disabled={sendingId === d.id}
                          onClick={() => void send(d)}
                        >
                          ✉
                        </button>
                      ) : (
                        <Link
                          href="/settings#delivery"
                          className="feed-tool"
                          title="Send to e-reader — set up delivery in Settings first"
                          aria-label={`Set up delivery to send ${d.title}`}
                        >
                          ✉
                        </Link>
                      ))}
                    {d.status === "ready" && (
                      <button
                        type="button"
                        className="feed-tool"
                        title="Press again for another device"
                        aria-label={`Recompile ${d.title}`}
                        aria-expanded={recompileFor === d.id}
                        disabled={recompiling}
                        onClick={() => openRecompile(d)}
                      >
                        ↻
                      </button>
                    )}
                    <button
                      type="button"
                      className="feed-tool danger"
                      aria-label={`Delete edition ${d.title}`}
                      title="Delete edition"
                      onClick={() => setDeleteTarget(d)}
                    >
                      ×
                    </button>
                  </span>
                </div>
                {recompileFor === d.id && (
                  <div className="recompile-panel">
                    {(settings?.profiles.length ?? 0) > 0 && (
                      <div>
                        <span className="feed-form-label">Press again for</span>
                        <div className="segmented" role="group" aria-label="Device profiles">
                          {(settings?.profiles ?? []).map((p) => (
                            <button
                              key={p.name}
                              type="button"
                              role="checkbox"
                              aria-checked={recompileProfiles.includes(p.name)}
                              className={`segmented-option ${
                                recompileProfiles.includes(p.name) ? "active" : ""
                              }`}
                              onClick={() => toggleRecompileProfile(p.name)}
                            >
                              {p.name}
                            </button>
                          ))}
                        </div>
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
                            ] as ["combined" | "per_group", string][]
                          ).map(([value, label]) => (
                            <button
                              key={value}
                              type="button"
                              role="radio"
                              aria-checked={recompileSplit === value}
                              className={`segmented-option ${
                                recompileSplit === value ? "active" : ""
                              }`}
                              onClick={() => setRecompileSplit(value)}
                            >
                              {label}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    <div className="recompile-panel-actions">
                      <button
                        type="button"
                        className="btn btn-sm"
                        disabled={
                          recompiling ||
                          ((settings?.profiles.length ?? 0) > 0 && recompileProfiles.length === 0)
                        }
                        onClick={() => void recompile(d)}
                      >
                        <span>
                          {recompileProfiles.length > 1
                            ? `Press ${recompileProfiles.length} editions`
                            : "Press edition"}
                        </span>
                        <span className="btn-arrow">→</span>
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => setRecompileFor(null)}
                      >
                        <span>Cancel</span>
                        <span className="btn-arrow">×</span>
                      </button>
                    </div>
                  </div>
                )}
                {previewId === d.id && (
                  <EditionPreview
                    digestId={d.id}
                    notify={(msg, kind) => toast(msg, kind === "error" ? "error" : undefined)}
                    onChanged={() => void refresh()}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </main>
      <ConfirmDialog
        open={deleteTarget !== null}
        title={`Delete edition ${deleteTarget?.title ?? ""}?`}
        body="The edition and its EPUB file will be removed. Articles stay in your library."
        confirmLabel="Delete edition"
        onConfirm={() => void remove()}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
