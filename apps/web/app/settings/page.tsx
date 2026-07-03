"use client";

import { useEffect, useState } from "react";
import { Masthead } from "../../components/Masthead";
import { ScanlineToggle } from "../../components/ScanlineToggle";
import { useToast } from "../../components/Toasts";
import { api, type AppSettings, type RenderProfile } from "../../lib/api";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export default function Settings() {
  const toast = useToast();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [saved, setSaved] = useState<AppSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [sendToDraft, setSendToDraft] = useState("");
  const [opdsBase, setOpdsBase] = useState("");
  const [opdsHttpsBase, setOpdsHttpsBase] = useState("");

  useEffect(() => {
    api.getSettings().then(
      (s) => {
        setSettings(s);
        setSaved(s);
      },
      (e) => {
        const message = e instanceof Error ? e.message : "could not load settings";
        setLoadError(message);
        toast(message, "error");
      },
    );
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
          {loadError ? (
            <p className="empty-state">
              Settings unavailable
              <small>{loadError}</small>
            </p>
          ) : (
            <p className="article-body-loading">Loading settings</p>
          )}
        </main>
      </div>
    );
  }

  const dirty = saved !== null && JSON.stringify(settings) !== JSON.stringify(saved);

  const set = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) =>
    setSettings((prev) => (prev ? { ...prev, [key]: value } : prev));

  const save = async () => {
    setSaving(true);
    try {
      const next = await api.putSettings(settings);
      setSettings(next);
      setSaved(next);
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
      const next = await api.putSettings(settings);
      setSettings(next);
      setSaved(next);
      const r = await api.testEmail();
      toast(`Test email sent to ${r.sent_to.join(", ")}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "test failed", "error");
    } finally {
      setTesting(false);
    }
  };

  const setProfile = (index: number, patch: Partial<RenderProfile>) =>
    set(
      "profiles",
      settings.profiles.map((p, i) => (i === index ? { ...p, ...patch } : p)),
    );

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
            <h2 className="content-title">Settings</h2>
          </div>
        </div>

        <div className="settings-layout">
          <nav className="settings-nav" aria-label="Settings sections">
            <a href="#delivery">Delivery</a>
            <a href="#compiling">Compiling</a>
            <a href="#library">Library</a>
            <a href="#fetching">Fetching</a>
            <a href="#appearance">Appearance</a>
          </nav>

          <div className="settings-sections">
            <section id="delivery" className="settings-section" aria-label="Delivery">
              <h3 className="settings-section-title">Delivery</h3>

              <div className="settings-subsection" aria-label="Email delivery">
                <h4>Send-to-Kindle email</h4>
                <p className="settings-hint">
                  Works for Kindle and PocketBook gateways, or any plain inbox.
                </p>
                <details className="settings-help">
                  <summary>How to set this up</summary>
                  <ol className="wizard">
              <li>
                Find your reader&apos;s address: Kindle owners: it&apos;s under{" "}
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
                </details>

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
              </div>

              <div className="settings-subsection" aria-label="OPDS">
                <h4>OPDS catalog</h4>
                <p className="settings-hint">
                  For KOReader, Xteink/CrossPoint, Kobo, Boox and Calibre: add this catalog URL in
                  the reader.
                </p>
                <code className="opds-url">{opdsBase}/opds</code>
                <p className="settings-hint">
                  Readers that only accept <strong>https://</strong> (e.g. Crosspoint) can use the
                  TLS endpoint; its certificate is self-signed, so enable &ldquo;skip/ignore
                  certificate&rdquo; on the device.
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
                  Some reader firmwares don&apos;t support authenticated OPDS, so leave auth off on
                  a trusted LAN.
                </p>
              </div>
            </section>

            <section id="compiling" className="settings-section" aria-label="Compiling">
              <h3 className="settings-section-title">Compiling</h3>

              <div className="settings-subsection" aria-label="Press deadline">
                <h4>Press deadline</h4>
                <p className="settings-hint">
                  At the deadline, everything in the queue is pressed into an edition
                  automatically. The queue must be non-empty; you still pick every article.
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
            {settings.deadline_enabled && settings.profiles.length > 0 && (
              <div>
                <span className="feed-form-label">Device profiles to press</span>
                {settings.profiles.map((p) => (
                  <label key={p.name} className="filter-toggle">
                    <input
                      type="checkbox"
                      className="checkbox"
                      checked={settings.deadline_profiles.includes(p.name)}
                      onChange={(e) =>
                        set(
                          "deadline_profiles",
                          e.target.checked
                            ? [...settings.deadline_profiles, p.name]
                            : settings.deadline_profiles.filter((n) => n !== p.name),
                        )
                      }
                    />
                    <span>{p.name}</span>
                  </label>
                ))}
                <p className="settings-hint">
                  None selected = one edition with the global settings.
                </p>
              </div>
            )}
              </div>

              <div className="settings-subsection" aria-label="Device profiles">
                <h4>Device profiles</h4>
                <p className="settings-hint">
                  A profile bundles per-device rendering choices. The default profile is what
                  &ldquo;Compile&rdquo; presses unless you choose otherwise; each profile also gets
                  its own OPDS folder (<code>/opds/profiles/…</code>).
                </p>
            {settings.profiles.map((p, i) => (
              <div key={i} className="field-grid">
                <label className="filter-toggle profile-default-toggle">
                  <input
                    type="radio"
                    name="default-profile"
                    className="checkbox"
                    checked={
                      settings.default_profile === p.name ||
                      (settings.default_profile === "" && i === 0)
                    }
                    onChange={() => set("default_profile", p.name)}
                  />
                  <span>Default profile</span>
                </label>
                <label>
                  <span className="feed-form-label">Name</span>
                  <input
                    value={p.name}
                    onChange={(e) => {
                      const next = e.target.value;
                      if (settings.default_profile === p.name) {
                        set("default_profile", next);
                      }
                      setProfile(i, { name: next });
                    }}
                  />
                </label>
                <label>
                  <span className="feed-form-label">Link QR codes</span>
                  <select
                    value={p.link_qr}
                    onChange={(e) =>
                      setProfile(i, { link_qr: e.target.value as RenderProfile["link_qr"] })
                    }
                  >
                    <option value="off">Off (keep links as text)</option>
                    <option value="articles">Article source links only</option>
                    <option value="all">All links in the article</option>
                  </select>
                </label>
                <label>
                  <span className="feed-form-label">Tables</span>
                  <select
                    value={p.table_mode}
                    onChange={(e) =>
                      setProfile(i, { table_mode: e.target.value as RenderProfile["table_mode"] })
                    }
                  >
                    <option value="native">Native HTML tables</option>
                    <option value="image">Render as image (auto-rotated to fit)</option>
                  </select>
                </label>
                <label>
                  <span className="feed-form-label">Screen size (px, optional)</span>
                  <span className="settings-inline-inputs">
                    <input
                      type="number"
                      min={1}
                      placeholder="width"
                      value={p.screen_width ?? ""}
                      onChange={(e) =>
                        setProfile(i, {
                          screen_width: e.target.value ? Number(e.target.value) : null,
                        })
                      }
                    />
                    <input
                      type="number"
                      min={1}
                      placeholder="height"
                      value={p.screen_height ?? ""}
                      onChange={(e) =>
                        setProfile(i, {
                          screen_height: e.target.value ? Number(e.target.value) : null,
                        })
                      }
                    />
                  </span>
                </label>
                <label>
                  <span className="feed-form-label">Code blocks</span>
                  <select
                    value={p.code_mode}
                    onChange={(e) =>
                      setProfile(i, { code_mode: e.target.value as RenderProfile["code_mode"] })
                    }
                  >
                    <option value="native">Native &lt;pre&gt; (most readers)</option>
                    <option value="br">Baked-in line breaks</option>
                    <option value="image">Render as image (Xteink X4)</option>
                  </select>
                </label>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    if (settings.default_profile === p.name) {
                      set("default_profile", "");
                    }
                    set(
                      "profiles",
                      settings.profiles.filter((_, j) => j !== i),
                    );
                  }}
                >
                  <span>Remove profile</span>
                  <span className="btn-arrow">×</span>
                </button>
              </div>
            ))}
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() =>
                set("profiles", [
                  ...settings.profiles,
                  {
                    name: "New device",
                    link_qr: "articles",
                    table_mode: "native",
                    code_mode: "native",
                    screen_width: null,
                    screen_height: null,
                  },
                ])
              }
            >
              <span>Add profile</span>
              <span className="btn-arrow">＋</span>
            </button>
                <p className="settings-hint">
                  Table/code pre-rendering helps readers with no CSS support. With a screen size
                  set, images are fitted to the device: wide blocks rotate 90°, tall ones split
                  into screen-shaped parts, photos downscale to 2× screen width. Existing editions
                  keep the profile they were pressed with.
                </p>
              </div>
            </section>

            <section id="library" className="settings-section" aria-label="Library">
              <h3 className="settings-section-title">Library</h3>
              <div className="settings-subsection">
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
                <option value="off">Off (keep links as text)</option>
                <option value="articles">Article source links only</option>
                <option value="all">All links in the article</option>
              </select>
            </label>
                <p className="settings-hint">
                  Many e-readers can&apos;t open embedded links; a QR code next to the link lets
                  you scan it with your phone instead.
                </p>
              </div>
            </section>

            <section id="fetching" className="settings-section" aria-label="Fetching">
              <h3 className="settings-section-title">Fetching</h3>

              <div className="settings-subsection" aria-label="Polling">
                <h4>Feed polling</h4>
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
                  Failing feeds back off automatically and show a ▲ badge in the sidebar.
                </p>
              </div>

              <div className="settings-subsection" aria-label="Reader fallback">
                <h4>Reader fallback</h4>
                <p className="settings-hint">
                  Some sites block server-side fetches. When the built-in fetch fails, hand the
                  link to an external reader service to pull the full text.
                </p>
            <label>
              <span className="feed-form-label">Fallback service</span>
              <select
                value={settings.reader_fallback}
                onChange={(e) =>
                  set("reader_fallback", e.target.value as AppSettings["reader_fallback"])
                }
              >
                <option value="none">None (feed summary only)</option>
                <option value="jina">Jina Reader (free, no key)</option>
                <option value="tavily">Tavily (API key, richer extraction)</option>
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
              </div>
            </section>

            <section id="appearance" className="settings-section" aria-label="Appearance">
              <h3 className="settings-section-title">Appearance</h3>
              <div className="settings-subsection">
                <p className="settings-hint">
                  The CRT scanline overlay is a purely visual texture, stored in this browser only.
                </p>
                <ScanlineToggle />
              </div>
            </section>
          </div>
        </div>

        {dirty && (
          <div className="settings-savebar" role="status">
            <span className="settings-savebar-hint">Unsaved changes</span>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setSettings(saved)}
              disabled={saving}
            >
              <span>Discard</span>
              <span className="btn-arrow">×</span>
            </button>
            <button type="button" className="btn" onClick={() => void save()} disabled={saving}>
              <span>{saving ? "Saving…" : "Save settings"}</span>
              <span className="btn-arrow">→</span>
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
