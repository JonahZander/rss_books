"use client";

import { useState } from "react";
import Link from "next/link";

type Props = {
  hasFeeds: boolean;
  hasQueuedEver: boolean;
  hasEdition: boolean;
  deliveryReady: boolean;
  onFocusAddFeed: () => void;
  onGoToQueue: () => void;
};

const DISMISS_KEY = "onboarding-dismissed";

export function OnboardingChecklist({
  hasFeeds,
  hasQueuedEver,
  hasEdition,
  deliveryReady,
  onFocusAddFeed,
  onGoToQueue,
}: Props) {
  const [dismissed, setDismissed] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(DISMISS_KEY) === "1";
  });

  const milestones = [hasFeeds, hasQueuedEver, hasEdition, deliveryReady];
  const done = milestones.filter(Boolean).length;
  // Server truth is recomputed on every load, so a stale dismissal can never
  // hide a checklist that still has work left in it — only a fully-complete
  // run stays hidden unconditionally.
  if (dismissed || done === milestones.length) return null;

  const dismiss = () => {
    window.localStorage.setItem(DISMISS_KEY, "1");
    setDismissed(true);
  };

  return (
    <div className="onboarding-card">
      <div className="onboarding-head">
        <span className="eyebrow eyebrow-ink">First edition</span>
        <button
          type="button"
          className="feed-tool"
          aria-label="Dismiss the first-edition checklist"
          title="Dismiss"
          onClick={dismiss}
        >
          ×
        </button>
      </div>
      <p className="onboarding-progress">Getting the desk running · {done}/4</p>
      <ul className="onboarding-list">
        <li className={`onboarding-item ${hasFeeds ? "done" : ""}`}>
          <span
            className={`checkbox onboarding-tick ${hasFeeds ? "checkbox-done" : ""}`}
            aria-hidden="true"
          />
          <span className="onboarding-item-body">
            <span className="visually-hidden">{hasFeeds ? "Done: " : "To do: "}</span>
            <span>Add a feed, or import an OPML file</span>
            {!hasFeeds && (
              <span className="settings-hint">
                No feeds yet? Import a starter list from the sidebar (example-feeds.opml), or
                add one by URL.
              </span>
            )}
          </span>
          {!hasFeeds && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={onFocusAddFeed}>
              <span>Add a feed</span>
              <span className="btn-arrow">→</span>
            </button>
          )}
        </li>
        <li className={`onboarding-item ${hasQueuedEver ? "done" : ""}`}>
          <span
            className={`checkbox onboarding-tick ${hasQueuedEver ? "checkbox-done" : ""}`}
            aria-hidden="true"
          />
          <span className="onboarding-item-body">
            <span className="visually-hidden">{hasQueuedEver ? "Done: " : "To do: "}</span>
            <span>Tick an article into the queue</span>
            {!hasQueuedEver && (
              <span className="settings-hint">
                Tick the checkbox on any article in the list to queue it for the next edition.
              </span>
            )}
          </span>
        </li>
        <li className={`onboarding-item ${hasEdition ? "done" : ""}`}>
          <span
            className={`checkbox onboarding-tick ${hasEdition ? "checkbox-done" : ""}`}
            aria-hidden="true"
          />
          <span className="onboarding-item-body">
            <span className="visually-hidden">{hasEdition ? "Done: " : "To do: "}</span>
            <span>Compile the queue into an edition</span>
          </span>
          {hasFeeds && !hasEdition && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={onGoToQueue}>
              <span>Go to queue</span>
              <span className="btn-arrow">→</span>
            </button>
          )}
        </li>
        <li className={`onboarding-item ${deliveryReady ? "done" : ""}`}>
          <span
            className={`checkbox onboarding-tick ${deliveryReady ? "checkbox-done" : ""}`}
            aria-hidden="true"
          />
          <span className="onboarding-item-body">
            <span className="visually-hidden">{deliveryReady ? "Done: " : "To do: "}</span>
            <span>Set up delivery to your e-reader</span>
          </span>
          {!deliveryReady && (
            <Link href="/settings#delivery" className="btn btn-ghost btn-sm">
              <span>Set up delivery</span>
              <span className="btn-arrow">→</span>
            </Link>
          )}
        </li>
      </ul>
    </div>
  );
}
