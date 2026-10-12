/** Company colours -> CSS variables, with readable text colours computed from luminance. */

function rgb(hex: string): [number, number, number] {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function toHex([r, g, b]: number[]): string {
  return "#" + [r, g, b].map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join("");
}

/** Mix with black (amount < 0) or white (amount > 0), amount in -1..1. */
export function shade(hex: string, amount: number): string {
  const target = amount < 0 ? 0 : 255;
  const a = Math.abs(amount);
  return toHex(rgb(hex).map((c) => c + (target - c) * a));
}

function luminance(hex: string): number {
  const [r, g, b] = rgb(hex).map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Black or white, whichever reads better on the colour. */
export function textOn(hex: string): string {
  return luminance(hex) > 0.4 ? "#0f172a" : "#ffffff";
}

const VALID = /^#[0-9a-fA-F]{6}$/;

export function dashboardVars(primary?: string, sidebar?: string): Record<string, string> {
  const p = primary && VALID.test(primary) ? primary : "#0e7490";
  const s = sidebar && VALID.test(sidebar) ? sidebar : "#0b1f2a";
  return {
    "--brand": p,
    "--brand-dark": shade(p, -0.2),
    "--brand-soft": shade(p, 0.9),
    "--on-brand": textOn(p),
    "--sidebar": s,
    "--sidebar-text": textOn(s),
  };
}

export function storefrontVars(primary?: string, accent?: string): Record<string, string> {
  const p = primary && VALID.test(primary) ? primary : "#0e7490";
  const a = accent && VALID.test(accent) ? accent : "#22d3ee";
  return {
    "--brand": p,
    "--brand-dark": shade(p, -0.25),
    "--brand-deep": shade(p, -0.6),
    "--brand-soft": shade(p, 0.9),
    "--on-brand": textOn(p),
    "--accent": a,
    "--on-accent": textOn(a),
  };
}
