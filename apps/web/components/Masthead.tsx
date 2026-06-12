"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

type Readouts = {
  feedCount: number;
  articleCount: number;
  queueCount: number;
};

type Props = {
  readouts?: Readouts;
};

const NAV = [
  { href: "/", label: "Triage" },
  { href: "/editions", label: "Editions" },
  { href: "/settings", label: "Settings" },
];

function Readout({ label, value, amber }: { label: string; value: string; amber?: boolean }) {
  const [pop, setPop] = useState(false);
  const prev = useRef(value);
  useEffect(() => {
    if (prev.current !== value) {
      prev.current = value;
      setPop(true);
      const id = window.setTimeout(() => setPop(false), 300);
      return () => window.clearTimeout(id);
    }
  }, [value]);
  return (
    <div className="readout">
      <span className="readout-label">{label}</span>
      <span className={`readout-value ${amber ? "amber" : ""} ${pop ? "pop" : ""}`}>{value}</span>
    </div>
  );
}

export function Masthead({ readouts }: Props) {
  const pathname = usePathname();
  const [clock, setClock] = useState<string>("--:--:--");

  useEffect(() => {
    const tick = () => {
      const d = new Date();
      const hh = String(d.getHours()).padStart(2, "0");
      const mm = String(d.getMinutes()).padStart(2, "0");
      const ss = String(d.getSeconds()).padStart(2, "0");
      setClock(`${hh}:${mm}:${ss}`);
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  const pad2 = (n: number) => String(n).padStart(2, "0");
  const pad3 = (n: number) => String(n).padStart(3, "0");

  return (
    <header className="masthead">
      <div>
        <h1 className="masthead-title">
          RSS<span className="slash">/</span>Kindle Selector
        </h1>
        <div className="masthead-sub">
          <span>Model&nbsp;RKS&#8209;01</span>
          <span className="dot" aria-hidden />
          <span>Self&#8209;hosted news desk</span>
          <span className="dot" aria-hidden />
          <nav className="masthead-nav" aria-label="Primary">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-link ${pathname === item.href ? "active" : ""}`}
                aria-current={pathname === item.href ? "page" : undefined}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </div>

      <div className="masthead-readout">
        {readouts && (
          <>
            <Readout label="Feeds" value={pad2(readouts.feedCount)} />
            <Readout label="Articles" value={pad3(readouts.articleCount)} />
            <Readout label="Queue" value={pad2(readouts.queueCount)} amber={readouts.queueCount > 0} />
          </>
        )}
        <span className="clock" aria-label="local time">
          {clock}
        </span>
      </div>
    </header>
  );
}
