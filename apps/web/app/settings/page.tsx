"use client";

import { useEffect, useState } from "react";
import { Masthead } from "../../components/Masthead";
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

  useEffect(() => {
    api.getSettings().then(setSettings, (e) => {
      toast(e instanceof Error ? e.message : "could not load settings", "error");
    });
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOpdsBase(window.location.origin);
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
              <span>Expanding an article marks it read</span>
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
          </section>
        </div>
      </main>
    </div>
  );
}
