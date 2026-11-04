import { KeyboardEvent, ReactNode, useState } from "react";

/** Dashboard chart colours (design handoff): website, WhatsApp, AI ring; ordinal funnel blues; booked-value line.
 *  They are CSS variables (styles/base.css) with one value per theme, each mark at least 3:1 against the card:
 *  dark — web #2a78d6 4.1, WhatsApp #eb6834 5.6, Instagram #c13584 3.5, AI #1baf7a 6.4;
 *  light — web #2a78d6 4.4, WhatsApp #d0542a 4.2, Instagram #c13584 5.1, AI #11865c 4.6 (on white). */
export const CHART = {
  web: "var(--chart-web)",
  wa: "var(--chart-wa)",
  ig: "var(--chart-ig)",
  ai: "var(--chart-ai)",
  line: "var(--chart-line)",
  funnel: ["var(--chart-funnel-1)", "var(--chart-funnel-2)", "var(--chart-funnel-3)"],
};
const GLOW = (color: string) => `drop-shadow(0 0 6px color-mix(in srgb, ${color} calc(var(--chart-glow) * 100%), transparent))`;

export interface DayPoint {
  /** Short label for the axis ("19 Sep"). */
  label: string;
  /** Label for the tooltip ("Sat 19 Sep"). */
  long: string;
  web: number;
  wa: number;
  ig: number;
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

/** Stacked columns per day: website at the bottom, WhatsApp, then Instagram on top. Hovering a day dims
 *  the others and shows a paper tooltip. `a` (0..1) animates the heights. */
export function DayColumns({ days, a, webLabel, waLabel, igLabel, axisEnd, ariaLabel }: {
  days: DayPoint[];
  a: number;
  webLabel: string;
  waLabel: string;
  igLabel: string;
  axisEnd: string;
  ariaLabel: string;
}) {
  const n = days.length;
  const [hover, setHover, onKey] = useKeyHover(n);
  const max = Math.max(1, ...days.map((d) => d.web + d.wa + d.ig));
  const gap = n > 30 ? 4 : n > 7 ? 7 : 18;
  const h = days[hover];
  return (
    <div className="dc-wrap" dir="ltr">
      <div className="dc-cols" style={{ gap }} tabIndex={0} role="img" aria-label={ariaLabel}
        onMouseLeave={() => setHover(-1)} onBlur={() => setHover(-1)} onKeyDown={onKey}>
        {days.map((d, i) => (
          <div key={i} className="dc-col" style={{ opacity: hover >= 0 && hover !== i ? 0.4 : 1 }} onMouseEnter={() => setHover(i)}>
            {d.ig > 0 && <div style={{ height: `${(d.ig / max) * 92 * a}%`, background: CHART.ig }} />}
            {d.wa > 0 && <div style={{ height: `${(d.wa / max) * 92 * a}%`, background: CHART.wa }} />}
            {d.web > 0 && <div style={{ height: `${(d.web / max) * 92 * a}%`, background: CHART.web }} />}
          </div>
        ))}
        {h && (
          <Tip at={((hover + 0.5) / n) * 100}>
            <b>{h.long}</b><br />{webLabel} {h.web} · {waLabel} {h.wa} · {igLabel} {h.ig}
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
            <stop offset="0" style={{ stopColor: CHART.line, stopOpacity: 0.45 }} />
            <stop offset="1" style={{ stopColor: CHART.line, stopOpacity: 0 }} />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#gjArea)" />
        <path d={line} fill="none" strokeWidth="2.5" vectorEffect="non-scaling-stroke"
          strokeLinejoin="round" style={{ stroke: CHART.line, filter: GLOW(CHART.line) }} />
        {hp && <line x1={xy[hover][0]} x2={xy[hover][0]} y1="0" y2="140" style={{ stroke: "var(--chart-guide)" }} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />}
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
      <circle cx="52" cy="52" r="42" fill="none" style={{ stroke: "var(--chart-track)" }} strokeWidth="10" />
      {v > 0 && (
        <circle cx="52" cy="52" r="42" fill="none" strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${(v * c * a).toFixed(1)} ${c}`} style={{ stroke: CHART.ai, filter: GLOW(CHART.ai) }} />
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
