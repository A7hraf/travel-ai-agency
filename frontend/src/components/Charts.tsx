import { KeyboardEvent, ReactNode, useState } from "react";

/** Dashboard chart colours (design handoff): website, WhatsApp, AI ring; ordinal funnel blues; booked-value line. */
export const CHART = {
  web: "#2a78d6",
  wa: "#eb6834",
  ai: "#1baf7a",
  line: "#4fb6dc",
  funnel: ["#2a78d6", "#5b9be6", "#9cc3f0"],
};

export interface DayPoint {
  /** Short label for the axis ("19 Sep"). */
  label: string;
  /** Label for the tooltip ("Sat 19 Sep"). */
  long: string;
  web: number;
  wa: number;
}

/** Paper tooltip positioned over a chart (percent from the inline start of an LTR chart box). */
function Tip({ at, children }: { at: number; children: ReactNode }) {
  const shift = at < 14 ? "0%" : at > 86 ? "-100%" : "-50%";
  return <div className="dc-tip" style={{ left: `${at}%`, transform: `translateX(${shift})` }} role="status">{children}</div>;
}

/** Arrow keys move the highlighted day of a chart that has the keyboard focus. */
function useKeyHover(n: number): [number, (i: number) => void, (e: KeyboardEvent) => void] {
  const [hover, setHover] = useState(-1);
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const d = e.key === "ArrowRight" ? 1 : -1;
      setHover((h) => Math.max(0, Math.min(n - 1, (h < 0 ? (d > 0 ? -1 : n) : h) + d)));
    } else if (e.key === "Escape") setHover(-1);
  };
  return [hover, setHover, onKey];
}

/** Stacked columns per day: website at the bottom, WhatsApp on top. Hovering a day dims the others
 *  and shows a paper tooltip. `a` (0..1) animates the heights. */
export function DayColumns({ days, a, webLabel, waLabel, axisEnd, ariaLabel }: {
  days: DayPoint[];
  a: number;
  webLabel: string;
  waLabel: string;
  axisEnd: string;
  ariaLabel: string;
}) {
  const n = days.length;
  const [hover, setHover, onKey] = useKeyHover(n);
  const max = Math.max(1, ...days.map((d) => d.web + d.wa));
  const gap = n > 30 ? 4 : n > 7 ? 7 : 18;
  const h = days[hover];
  return (
    <div className="dc-wrap" dir="ltr">
      <div className="dc-cols" style={{ gap }} tabIndex={0} role="img" aria-label={ariaLabel}
        onMouseLeave={() => setHover(-1)} onBlur={() => setHover(-1)} onKeyDown={onKey}>
        {days.map((d, i) => (
          <div key={i} className="dc-col" style={{ opacity: hover >= 0 && hover !== i ? 0.4 : 1 }} onMouseEnter={() => setHover(i)}>
            {d.wa > 0 && <div style={{ height: `${(d.wa / max) * 92 * a}%`, background: CHART.wa }} />}
            {d.web > 0 && <div style={{ height: `${(d.web / max) * 92 * a}%`, background: CHART.web }} />}
          </div>
        ))}
        {h && (
          <Tip at={((hover + 0.5) / n) * 100}>
            <b>{h.long}</b><br />{webLabel} {h.web} · {waLabel} {h.wa}
          </Tip>
        )}
      </div>
      {n > 0 && (
        <div className="dc-axis"><span>{days[0].label}</span><span>{days[Math.floor(n / 2)].label}</span><span>{axisEnd}</span></div>
      )}
    </div>
  );
}

/** Area line (booked value per day): cyan line with a glow and a gradient fill from 45% to 0%. */
export function AreaChart({ points, a, format, ariaLabel }: {
  points: { long: string; value: number }[];
  a: number;
  format: (v: number) => ReactNode;
  ariaLabel: string;
}) {
  const n = points.length;
  const [hover, setHover, onKey] = useKeyHover(n);
  const max = Math.max(1, ...points.map((p) => p.value));
  const xy = points.map((p, i) => [n <= 1 ? 300 : (i / (n - 1)) * 600, 140 - (p.value / max) * 118 * a - 6]);
  const line = xy.length ? "M" + xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" L") : "";
  const area = line ? `${line} L600,140 L0,140 Z` : "";
  const onMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const i = Math.round(((e.clientX - box.left) / box.width) * (n - 1));
    setHover(Math.max(0, Math.min(n - 1, i)));
  };
  const hp = points[hover];
  return (
    <div className="dc-area" dir="ltr" tabIndex={0} role="img" aria-label={ariaLabel}
      onMouseMove={onMove} onMouseLeave={() => setHover(-1)} onBlur={() => setHover(-1)} onKeyDown={onKey}>
      <svg viewBox="0 0 600 140" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <linearGradient id="gjArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={CHART.line} stopOpacity="0.45" />
            <stop offset="1" stopColor={CHART.line} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#gjArea)" />
        <path d={line} fill="none" stroke={CHART.line} strokeWidth="2.5" vectorEffect="non-scaling-stroke"
          strokeLinejoin="round" style={{ filter: "drop-shadow(0 0 6px rgba(79,182,220,.7))" }} />
        {hp && <line x1={xy[hover][0]} x2={xy[hover][0]} y1="0" y2="140" stroke="rgba(243,242,242,.25)" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />}
      </svg>
      {hp && (
        <>
          <span className="dc-dot" style={{ left: `${(xy[hover][0] / 600) * 100}%`, top: `${(xy[hover][1] / 140) * 100}%` }} />
          <Tip at={(xy[hover][0] / 600) * 100}><b>{hp.long}</b><br />{format(hp.value)}</Tip>
        </>
      )}
    </div>
  );
}

/** AI ring: share handled fully by the AI. "—" when there is nothing to measure. */
export function Ring({ value, a, empty, label }: { value: number; a: number; empty?: boolean; label: string }) {
  const c = 263.9; // 2πr for r = 42
  const v = empty ? 0 : Math.max(0, Math.min(1, value));
  return (
    <svg width="88" height="88" viewBox="0 0 104 104" className="dc-ring" role="img" aria-label={label}>
      <circle cx="52" cy="52" r="42" fill="none" stroke="rgba(243,242,242,.1)" strokeWidth="10" />
      {v > 0 && (
        <circle cx="52" cy="52" r="42" fill="none" stroke={CHART.ai} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${(v * c * a).toFixed(1)} ${c}`} style={{ filter: "drop-shadow(0 0 6px rgba(27,175,122,.6))" }} />
      )}
    </svg>
  );
}

/** One horizontal meter (funnel rows, top packages). */
export function Meter({ ratio, color, a, height = 10 }: { ratio: number; color: string; a: number; height?: number }) {
  return (
    <div className="dc-meter" style={{ height, borderRadius: height / 2 }}>
      <div style={{ width: `${Math.max(0, Math.min(1, ratio)) * 100 * a}%`, background: color, borderRadius: height / 2 }} />
    </div>
  );
}
