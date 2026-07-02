"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { LogoMark } from "./LogoMark";

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

  return (
    <header className="masthead">
      <div>
        <h1 className="masthead-title">
          <LogoMark className="masthead-mark" />
          RSS <span className="brand-accent">Books</span>
        </h1>
        <div className="masthead-sub">
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
        {/* The article and queue counts live in the content header and queue
            rail respectively; the masthead carries only Feeds. */}
        {readouts && <Readout label="Feeds" value={String(readouts.feedCount)} />}
      </div>
    </header>
  );
}
