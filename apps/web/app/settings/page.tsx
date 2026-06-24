"use client";

import { useEffect, useState } from "react";
import { Masthead } from "../../components/Masthead";
import { ScanlineToggle } from "../../components/ScanlineToggle";
import { useToast } from "../../components/Toasts";
import { api, type AppSettings } from "../../lib/api";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export default function Settings() {
  const toast = useToast();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [sendToDraft, setSendToDraft] = useState("");
  const [opdsBase, setOpdsBase] = useState("");
  const [opdsHttpsBase, setOpdsHttpsBase] = useState("");

  useEffect(() => {
    api.getSettings().then(setSettings, (e) => {
      toast(e instanceof Error ? e.message : "could not load settings", "error");
    });
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOpdsBase(window.location.origin);
    // The container also serves HTTPS on :8443 for readers that only speak TLS
    // (e.g. Crosspoint forces https://). Same host, fixed TLS port.
    setOpdsHttpsBase(`https://${window.location.hostname}:8443`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!settings) {
    return (
      <div className="app">
        <Masthead />
        <main className="page-main">
          <p className="article-body-loading">Loading settings</p>
        </main>
      </div>
    );
  }

  const set = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) =>
    setSettings((prev) => (prev ? { ...prev, [key]: value } : prev));

  const save = async () => {
    setSaving(true);
    try {
      setSettings(await api.putSettings(settings));
      toast("Settings saved");
    } catch (e) {
      toast(e instanceof Error ? e.message : "save failed", "error");
    } finally {
      setSaving(false);
    }
  };

  const testEmail = async () => {
    setTesting(true);
    try {
      await api.putSettings(settings);
      const r = await api.testEmail();
      toast(`Test email sent to ${r.sent_to.join(", ")}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "test failed", "error");
    } finally {
      setTesting(false);
    }
  };

  const addSendTo = () => {
    const value = sendToDraft.trim();
    if (!value) return;
    if (!settings.send_to.includes(value)) {
      set("send_to", [...settings.send_to, value]);
    }
    setSendToDraft("");
  };

  return (
    <div className="app">
      <Masthead />
      <main className="page-main settings-main" aria-label="Settings">
        <div className="content-head">
          <div>
            <span className="eyebrow">05 — Configuration</span>
            <h2 className="content-title">Settings</h2>
          </div>
          <button type="button" className="btn" onClick={() => void save()} disabled={saving}>
            <span>{saving ? "Saving…" : "Save settings"}</span>
            <span className="btn-arrow">→</span>
          </button>
        </div>

        <div className="settings-grid">
          <section className="settings-card corner-marks" aria-label="Appearance">
            <p className="eyebrow eyebrow-ink">Appearance</p>
            <p className="settings-hint">
              The CRT scanline overlay is a purely visual texture, stored in this browser only.
            </p>
            <ScanlineToggle />
          </section>

          <section className="settings-card corner-marks" aria-label="Email delivery">
            <p className="eyebrow eyebrow-ink">Delivery · Send-to-Kindle email</p>
            <p className="settings-hint">
              Works for Kindle and PocketBook gateways — or any plain inbox.
            </p>
            <ol className="wizard">
              <li>
                Find your reader&apos;s address: Kindle owners — it&apos;s under{" "}
                <a
                  href="https://www.amazon.com/hz/mycd/digital-console/alldevices"
                  target="_blank"
                  rel="noreferrer"
                >
                  Manage Your Content &amp; Devices → Devices
                </a>{" "}
                (looks like <code>you_123@kindle.com</code>). Add it below.
              </li>
              <li>
                Approve the sender: in{" "}
                <a
                  href="https://www.amazon.com/hz/mycd/myx#/home/settings/payment"
                  target="_blank"
                  rel="noreferrer"
                >
                  Preferences → Personal Document Settings
                </a>
                , add your <strong>From address</strong> to the approved senders list.
              </li>
              <li>Send a test email. If it lands on the device, you&apos;re done.</li>
            </ol>

            <div className="field-grid">
              <label>
                <span className="feed-form-label">SMTP host</span>
                <input
                  value={settings.smtp_host}
                  onChange={(e) => set("smtp_host", e.target.value)}
                  placeholder="smtp.fastmail.com"
                />
              </label>
              <label>
                <span className="feed-form-label">Port</span>
                <input
                  type="number"
                  value={settings.smtp_port}
                  onChange={(e) => set("smtp_port", Number(e.target.value))}
                />
              </label>
              <label>
                <span className="feed-form-label">Security</span>
                <select
                  value={settings.smtp_security}
                  onChange={(e) =>
                    set("smtp_security", e.target.value as AppSettings["smtp_security"])
                  }
                >
                  <option value="starttls">STARTTLS (587)</option>
                  <option value="ssl">SSL/TLS (465)</option>
                  <option value="none">None</option>
                </select>
              </label>
              <label>
                <span className="feed-form-label">Username</span>
                <input
                  value={settings.smtp_username}
                  onChange={(e) => set("smtp_username", e.target.value)}
                  autoComplete="off"
                />
              </label>
              <label>
                <span className="feed-form-label">Password</span>
                <input
                  type="password"
                  value={settings.smtp_password}
                  onChange={(e) => set("smtp_password", e.target.value)}
                  autoComplete="new-password"
                />
              </label>
              <label>
                <span className="feed-form-label">From address</span>
                <input
                  value={settings.smtp_from}
                  onChange={(e) => set("smtp_from", e.target.value)}
                  placeholder="news@you.example"
                />
              </label>
            </div>

            <div>
              <span className="feed-form-label">Send to</span>
              <div className="chips">
                {settings.send_to.map((addr) => (
                  <span key={addr} className="chip">
                    {addr}
                    <button
                      type="button"
                      aria-label={`Remove ${addr}`}
                      onClick={() =>
                        set(
                          "send_to",
                          settings.send_to.filter((a) => a !== addr),
                        )
                      }
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
              <div className="chip-input-row">
                <input
                  value={sendToDraft}
                  onChange={(e) => setSendToDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addSendTo();
                    }
                  }}
                  placeholder="you_123@kindle.com"
                  aria-label="Add destination address"
                />
                <button type="button" className="btn btn-ghost btn-sm" onClick={addSendTo}>
                  <span>Add</span>
                </button>
              </div>
            </div>

            <label className="filter-toggle">
              <input
                type="checkbox"
                className="checkbox"
                checked={settings.email_on_ready}
                onChange={(e) => set("email_on_ready", e.target.checked)}
              />
              <span>Email every edition when it&apos;s ready (incl. press-deadline editions)</span>
            </label>

            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => void testEmail()}
              disabled={testing}
            >
              <span>{testing ? "Sending…" : "Save & send test email"}</span>
              <span className="btn-arrow">✉</span>
            </button>
          </section>

          <section className="settings-card corner-marks" aria-label="OPDS">
            <p className="eyebrow eyebrow-ink">Delivery · OPDS catalog</p>
            <p className="settings-hint">
              For KOReader (incl. jailbroken Kindles), Xteink/CrossPoint, Kobo, Boox and Calibre:
              add this catalog URL in the reader.
            </p>
            <code className="opds-url">{opdsBase}/opds</code>
            <p className="settings-hint">
              If your reader only accepts <strong>https://</strong> (e.g. Crosspoint), use the
              TLS endpoint instead. It serves a self-signed certificate, so enable
              &ldquo;skip/ignore certificate&rdquo; on the device if it offers it.
            </p>
            <code className="opds-url">{opdsHttpsBase}/opds</code>
            <label className="filter-toggle">
              <input
                type="checkbox"
                className="checkbox"
                checked={settings.opds_auth_enabled}
                onChange={(e) => set("opds_auth_enabled", e.target.checked)}
              />
              <span>Require HTTP Basic auth on the catalog</span>
            </label>
            {settings.opds_auth_enabled && (
              <div className="field-grid">
                <label>
                  <span className="feed-form-label">Username</span>
                  <input
                    value={settings.opds_username}
                    onChange={(e) => set("opds_username", e.target.value)}
                  />
                </label>
                <label>
                  <span className="feed-form-label">Password</span>
                  <input
                    type="password"
                    value={settings.opds_password}
                    onChange={(e) => set("opds_password", e.target.value)}
                  />
                </label>
              </div>
            )}
            <p className="settings-hint">
              Note: some reader firmwares don&apos;t support authenticated OPDS — leave this off on
              a trusted LAN.
            </p>
          </section>

          <section className="settings-card corner-marks" aria-label="Polling">
            <p className="eyebrow eyebrow-ink">Polling</p>
            <label className="filter-toggle">
              <input
                type="checkbox"
                className="checkbox"
                checked={settings.poll_enabled}
                onChange={(e) => set("poll_enabled", e.target.checked)}
              />
              <span>Poll feeds automatically in the background</span>
            </label>
            <label>
              <span className="feed-form-label">Default interval (minutes)</span>
              <input
                type="number"
                min={1}
                value={settings.default_poll_minutes}
                onChange={(e) => set("default_poll_minutes", Number(e.target.value))}
              />
            </label>
            <p className="settings-hint">
              Failing feeds back off automatically (interval × 2 per failure, capped at 24 h) and
              show a ▲ badge in the sidebar.
            </p>
          </section>

          <section className="settings-card corner-marks" aria-label="Press deadline">
            <p className="eyebrow eyebrow-ink">Press deadline</p>
            <p className="settings-hint">
              At the deadline, everything in the queue is pressed into an edition automatically —
              the Friday-paper ritual. The queue must be non-empty; you still pick every article.
            </p>
            <label className="filter-toggle">
              <input
                type="checkbox"
                className="checkbox"
                checked={settings.deadline_enabled}
                onChange={(e) => set("deadline_enabled", e.target.checked)}
              />
              <span>Compile the queue on a schedule</span>
            </label>
            {settings.deadline_enabled && (
              <div className="field-grid">
                <label>
                  <span className="feed-form-label">Cadence</span>
                  <select
                    value={settings.deadline_type}
                    onChange={(e) =>
                      set("deadline_type", e.target.value as AppSettings["deadline_type"])
                    }
                  >
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                  </select>
                </label>
                {settings.deadline_type === "weekly" && (
                  <label>
                    <span className="feed-form-label">Day</span>
                    <select
                      value={settings.deadline_weekday}
                      onChange={(e) => set("deadline_weekday", Number(e.target.value))}
                    >
                      {WEEKDAYS.map((day, i) => (
                        <option key={day} value={i}>
                          {day}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <label>
                  <span className="feed-form-label">Time (server clock)</span>
                  <input
                    type="time"
                    value={settings.deadline_time}
                    onChange={(e) => set("deadline_time", e.target.value)}
                  />
                </label>
                <label>
                  <span className="feed-form-label">Edition mode</span>
                  <select
                    value={settings.deadline_split}
                    onChange={(e) =>
                      set("deadline_split", e.target.value as AppSettings["deadline_split"])
                    }
                  >
                    <option value="combined">One combined edition</option>
                    <option value="per_group">One edition per feed group</option>
                  </select>
                </label>
              </div>
            )}
          </section>

          <section className="settings-card corner-marks" aria-label="Library">
            <p className="eyebrow eyebrow-ink">Library</p>
            <label className="filter-toggle">
              <input
                type="checkbox"
                className="checkbox"
                checked={settings.mark_read_on_expand}
                onChange={(e) => set("mark_read_on_expand", e.target.checked)}
              />
              <span>Expanding an article marks it seen</span>
            </label>
            <label className="filter-toggle">
              <input
                type="checkbox"
                className="checkbox"
                checked={settings.retention_enabled}
                onChange={(e) => set("retention_enabled", e.target.checked)}
              />
              <span>Clean up old articles automatically</span>
            </label>
            {settings.retention_enabled && (
              <label>
                <span className="feed-form-label">Keep articles for (days)</span>
                <input
                  type="number"
                  min={1}
                  value={settings.retention_days}
                  onChange={(e) => set("retention_days", Number(e.target.value))}
                />
              </label>
            )}
            <p className="settings-hint">
              Queued articles and articles already pressed into editions are never cleaned up.
            </p>
            <label>
              <span className="feed-form-label">Inline QR codes for links</span>
              <select
                value={settings.link_qr}
                onChange={(e) => set("link_qr", e.target.value as AppSettings["link_qr"])}
              >
                <option value="off">Off — keep links as text</option>
                <option value="articles">Article source links only</option>
                <option value="all">All links in the article</option>
              </select>
            </label>
            <p className="settings-hint">
              Many e-readers can&apos;t open embedded links. Adding a QR code next to a link lets
              you scan it with your phone instead. &ldquo;Article source links&rdquo; codes each
              piece&apos;s &ldquo;Read the original&rdquo; link; &ldquo;All links&rdquo; also codes
              every hyperlink in the body.
            </p>
          </section>

          <section className="settings-card corner-marks" aria-label="Reader fallback">
            <p className="eyebrow eyebrow-ink">Article fetching · Reader fallback</p>
            <p className="settings-hint">
              Many sites block server-side fetches — Cloudflare and friends fingerprint the
              connection itself, not just the user-agent. When the built-in fetch is blocked,
              hand the link to an external reader service to pull the full text. Only used when
              the direct fetch fails.
            </p>
            <label>
              <span className="feed-form-label">Fallback service</span>
              <select
                value={settings.reader_fallback}
                onChange={(e) =>
                  set("reader_fallback", e.target.value as AppSettings["reader_fallback"])
                }
              >
                <option value="none">None — feed summary only</option>
                <option value="jina">Jina Reader — free, no key</option>
                <option value="tavily">Tavily — API key, richer extraction</option>
              </select>
            </label>
            {settings.reader_fallback === "tavily" && (
              <label>
                <span className="feed-form-label">Tavily API key</span>
                <input
                  type="password"
                  value={settings.tavily_api_key}
                  onChange={(e) => set("tavily_api_key", e.target.value)}
                  placeholder="tvly-…"
                  autoComplete="off"
                />
              </label>
            )}
            {settings.reader_fallback !== "none" && (
              <p className="settings-hint">
                Heads up: the article URL is sent to{" "}
                {settings.reader_fallback === "tavily" ? "Tavily" : "Jina"}&apos;s servers to
                fetch the page.
              </p>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
