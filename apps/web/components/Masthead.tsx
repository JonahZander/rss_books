"use client";

import { useEffect, useState } from "react";

type Props = {
  feedCount: number;
  articleCount: number;
  queueCount: number;
};

export function Masthead({ feedCount, articleCount, queueCount }: Props) {
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
          <span>Edition 2026.04</span>
          <span className="dot" aria-hidden />
          <span>Local Node</span>
        </div>
      </div>

      <div className="masthead-readout">
        <div className="readout">
          <span className="readout-label">Feeds</span>
          <span className="readout-value">{pad2(feedCount)}</span>
        </div>
        <div className="readout">
          <span className="readout-label">Articles</span>
          <span className="readout-value">{pad3(articleCount)}</span>
        </div>
        <div className="readout">
          <span className="readout-label">Queue</span>
          <span className={`readout-value ${queueCount > 0 ? "amber" : ""}`}>
            {pad2(queueCount)}
          </span>
        </div>
        <span className="clock" aria-label="local time">
          {clock}
        </span>
      </div>
    </header>
  );
}
