import { ReactNode, useEffect, useRef, useState } from "react";

// Validated categorical palette (fixed order, never cycled) and an ordinal blue ramp.
export const SERIES = ["#2a78d6", "#eb6834", "#1baf7a"];
export const ORDINAL_BLUES = ["#86b6ef", "#3987e5", "#1c5cab"];

const AXIS = "#94a3b8";
const GRID = "#eef2f7";
const SURFACE = "#ffffff";

function useWidth<T extends HTMLElement>(): [React.RefObject<T>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(600);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.round(entry.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

/** Rounded "nice" maximum and 4 tick values for an axis starting at zero. */
function ticks(max: number): number[] {
  if (max <= 0) return [0, 1, 2, 3, 4];
  const raw = max / 4;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? raw;
  return [0, 1, 2, 3, 4].map((i) => +(i * step).toFixed(6));
}

/** Bar with only its data end rounded (4px), anchored on the baseline. */
function barPath(x: number, y: number, w: number, h: number, r = 4): string {
  if (h <= 0) return "";
  const rr = Math.min(r, h, w / 2);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

function hbarPath(x: number, y: number, w: number, h: number, r = 4, rtl = false): string {
  if (w <= 0) return "";
  const rr = Math.min(r, w, h / 2);
  if (rtl) {
    const x0 = x - w;
    return `M${x},${y}H${x0 + rr}Q${x0},${y} ${x0},${y + rr}V${y + h - rr}Q${x0},${y + h} ${x0 + rr},${y + h}H${x}Z`;
  }
  return `M${x},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h - rr}Q${x + w},${y + h} ${x + w - rr},${y + h}H${x}Z`;
}

interface Tip { x: number; y: number; content: ReactNode }

function Tooltip({ tip }: { tip: Tip | null }) {
  if (!tip) return null;
  return <div className="chart-tip" style={{ left: tip.x, top: tip.y }}>{tip.content}</div>;
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="chart-legend">
      {items.map((i) => (
        <span key={i.label}><i style={{ background: i.color }} />{i.label}</span>
      ))}
    </div>
  );
}

export interface Column { label: string; values: number[] }

/** Stacked columns over time (one colour per series, legend above). */
export function StackedColumns({ data, series, format = String, tooltipTitle }: {
  data: Column[];
  series: { label: string; color: string }[];
  format?: (v: number) => string;
  tooltipTitle?: (i: number) => string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const height = 220;
  const pad = { l: 34, r: 8, t: 10, b: 24 };
  const totals = data.map((d) => d.values.reduce((a, b) => a + b, 0));
  const tk = ticks(Math.max(...totals, 0));
  const top = tk[tk.length - 1];
  const plotW = width - pad.l - pad.r;
  const plotH = height - pad.t - pad.b;
  const slot = plotW / Math.max(1, data.length);
  const barW = Math.max(2, Math.min(24, slot * 0.66));
  const y = (v: number) => pad.t + plotH - (v / top) * plotH;
  const labelEvery = Math.ceil(data.length / Math.max(1, Math.floor(plotW / 56)));

  return (
    <div className="chart" ref={ref} dir="ltr" onMouseLeave={() => { setTip(null); setHover(null); }}>
      <svg width={width} height={height} role="img">
        {tk.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={width - pad.r} y1={y(v)} y2={y(v)} stroke={GRID} />
            <text x={pad.l - 6} y={y(v) + 4} textAnchor="end" className="chart-axis">{format(v)}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const cx = pad.l + slot * i + slot / 2;
          let base = 0;
          const visible = d.values.map((v, s) => ({ v, s })).filter((x) => x.v > 0);
          return (
            <g key={i} opacity={hover === null || hover === i ? 1 : 0.55}>
              {visible.map(({ v, s }, k) => {
                const y0 = y(base);
                base += v;
                const y1 = y(base);
                const isTop = k === visible.length - 1;
                const gap = k > 0 ? 2 : 0; // 2px surface gap between stacked segments
                const h = Math.max(0, y0 - y1 - gap);
                return isTop
                  ? <path key={s} d={barPath(cx - barW / 2, y1, barW, h)} fill={series[s].color} />
                  : <rect key={s} x={cx - barW / 2} y={y1} width={barW} height={h} fill={series[s].color} />;
              })}
              {i % labelEvery === 0 && (
                <text x={cx} y={height - 6} textAnchor="middle" className="chart-axis">{d.label}</text>
              )}
              <rect x={pad.l + slot * i} y={pad.t} width={slot} height={plotH} fill="transparent"
                onMouseMove={() => {
                  setHover(i);
                  setTip({
                    x: Math.min(cx + 12, width - 170), y: Math.max(0, y(totals[i]) - 10),
                    content: (
                      <>
                        <strong>{tooltipTitle ? tooltipTitle(i) : d.label}</strong>
                        {series.map((s, k) => (
                          <div key={s.label} className="tip-row"><i style={{ background: s.color }} />{s.label}<b>{format(d.values[k])}</b></div>
                        ))}
                      </>
                    ),
                  });
                }} />
            </g>
          );
        })}
        <line x1={pad.l} x2={width - pad.r} y1={y(0)} y2={y(0)} stroke={AXIS} />
      </svg>
      <Tooltip tip={tip} />
    </div>
  );
}

/** Single series line with a soft area, crosshair and tooltip. */
export function AreaLine({ data, color = SERIES[0], format = String, axisFormat, tooltipTitle }: {
  data: { label: string; value: number }[];
  color?: string;
  format?: (v: number) => string;
  axisFormat?: (v: number) => string;
  tooltipTitle?: (i: number) => string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const height = 220;
  const pad = { l: 46, r: 12, t: 12, b: 24 };
  const tk = ticks(Math.max(...data.map((d) => d.value), 0));
  const top = tk[tk.length - 1];
  const plotW = width - pad.l - pad.r;
  const plotH = height - pad.t - pad.b;
  const x = (i: number) => pad.l + (data.length <= 1 ? plotW / 2 : (plotW * i) / (data.length - 1));
  const y = (v: number) => pad.t + plotH - (v / top) * plotH;
  const line = data.map((d, i) => `${i ? "L" : "M"}${x(i)},${y(d.value)}`).join("");
  const area = data.length ? `${line}L${x(data.length - 1)},${y(0)}L${x(0)},${y(0)}Z` : "";
  const labelEvery = Math.ceil(data.length / Math.max(1, Math.floor(plotW / 56)));
  const gradId = `area-${color.slice(1)}`;
  const axis = axisFormat ?? format;

  const onMove = (e: React.MouseEvent<SVGRectElement>) => {
    const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
    const px = e.clientX - box.left;
    const i = Math.round(((px - pad.l) / plotW) * (data.length - 1));
    setHover(Math.max(0, Math.min(data.length - 1, i)));
  };

  return (
    <div className="chart" ref={ref} dir="ltr" onMouseLeave={() => setHover(null)}>
      <svg width={width} height={height} role="img">
        <defs>
          <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.22} />
            <stop offset="100%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        {tk.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={width - pad.r} y1={y(v)} y2={y(v)} stroke={GRID} />
            <text x={pad.l - 6} y={y(v) + 4} textAnchor="end" className="chart-axis">{axis(v)}</text>
          </g>
        ))}
        {data.map((d, i) => i % labelEvery === 0 && (
          <text key={i} x={x(i)} y={height - 6} textAnchor="middle" className="chart-axis">{d.label}</text>
        ))}
        <path d={area} fill={`url(#${gradId})`} />
        <path d={line} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        <line x1={pad.l} x2={width - pad.r} y1={y(0)} y2={y(0)} stroke={AXIS} />
        {hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={y(0)} stroke={AXIS} strokeDasharray="3 3" />
            <circle cx={x(hover)} cy={y(data[hover].value)} r={5} fill={color} stroke={SURFACE} strokeWidth={2} />
          </g>
        )}
        <rect x={pad.l} y={pad.t} width={plotW} height={plotH} fill="transparent" onMouseMove={onMove} />
      </svg>
      {hover !== null && (
        <Tooltip tip={{
          x: Math.min(x(hover) + 12, width - 170), y: Math.max(0, y(data[hover].value) - 40),
          content: <><strong>{tooltipTitle ? tooltipTitle(hover) : data[hover].label}</strong><div className="tip-row"><b>{format(data[hover].value)}</b></div></>,
        }} />
      )}
    </div>
  );
}

/** Horizontal bars with the value written next to each bar (text in ink, not the bar colour). */
export function HBars({ items, format = String, rtl = false }: {
  items: { label: string; value: number; color: string; note?: string }[];
  format?: (v: number) => string;
  rtl?: boolean;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const max = Math.max(...items.map((i) => i.value), 1);
  const rowH = 46;
  const barH = 20;
  const valueW = 110;
  const plotW = Math.max(40, width - valueW);
  const height = items.length * rowH;

  return (
    <div className="chart" ref={ref} dir="ltr" onMouseLeave={() => setTip(null)}>
      <svg width={width} height={height} role="img">
        {items.map((it, i) => {
          const w = (it.value / max) * plotW;
          const y = i * rowH + 18;
          const x0 = rtl ? width : 0;
          return (
            <g key={it.label} onMouseMove={() => setTip({
              x: rtl ? Math.max(0, width - w - 180) : Math.min(w + 8, width - 180), y: y - 30,
              content: <><strong>{it.label}</strong><div className="tip-row"><b>{format(it.value)}</b></div>{it.note && <div className="muted small">{it.note}</div>}</>,
            })}>
              <text x={rtl ? width : 0} y={y - 5} textAnchor={rtl ? "end" : "start"} className="chart-label">{it.label}</text>
              <rect x={rtl ? width - plotW : 0} y={y} width={plotW} height={barH} rx={4} fill="#f1f5f9" />
              <path d={hbarPath(x0, y, w, barH, 4, rtl)} fill={it.color} />
              <text x={rtl ? width - w - 8 : w + 8} y={y + 15} textAnchor={rtl ? "end" : "start"} className="chart-value">{format(it.value)}</text>
            </g>
          );
        })}
      </svg>
      <Tooltip tip={tip} />
    </div>
  );
}

/** Ring meter for one share (e.g. % handled by the AI). */
export function Ring({ value, color = SERIES[0], size = 78 }: { value: number; color?: string; size?: number }) {
  const r = size / 2 - 6;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, value));
  return (
    <svg width={size} height={size} className="ring" role="img" aria-label={`${Math.round(v * 100)}%`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e8eef6" strokeWidth={8} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={8} strokeLinecap="round"
        strokeDasharray={`${c * v} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" className="ring-text">{Math.round(v * 100)}%</text>
    </svg>
  );
}

/** "View as table" block under a chart. */
export function DataTable({ summary, head, rows }: { summary: string; head: string[]; rows: ReactNode[][] }) {
  return (
    <details className="chart-table">
      <summary>{summary}</summary>
      <div className="table-wrap">
        <table className="table">
          <thead><tr>{head.map((h) => <th key={h}>{h}</th>)}</tr></thead>
          <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </details>
  );
}
