/** Company colours -> CSS variables, with readable text colours computed from luminance. */

/** Ghanjah brand colours (brand kit v1.0). */
export const GHANJAH = {
  ink: "#201e1d",
  paper: "#f3f2f2",
  cyan: "#0088b0",
  magenta: "#d6006c",
  cyanOnDark: "#4fb6dc",
  magentaOnDark: "#ff5c9d",
};

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
export function isDark(hex: string): boolean {
  return luminance(VALID.test(hex) ? hex : GHANJAH.ink) <= 0.4;
}

export function textOn(hex: string): string {
  return luminance(hex) > 0.4 ? "#201e1d" : "#ffffff";
}

const VALID = /^#[0-9a-fA-F]{6}$/;

function rgba(hex: string, alpha: number): string {
  const [r, g, b] = rgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** The interface is dark: an agency colour is lightened until it reads well on the dark surfaces
 *  (contrast of at least 6:1 with Ink). Ghanjah's own colours use their official "on dark" versions. */
export function forDark(hex: string, min = 6): string {
  const lower = hex.toLowerCase();
  if (lower === GHANJAH.cyan) return GHANJAH.cyanOnDark;
  if (lower === GHANJAH.magenta) return GHANJAH.magentaOnDark;
  let out = hex;
  for (let step = 1; contrast(out, GHANJAH.ink) < min && step <= 12; step++) out = shade(hex, step * 0.07);
  return out;
}

function actionVars(name: "brand" | "agency-accent", base: string): Record<string, string> {
  return {
    [`--${name}`]: base,
    [`--${name}-hover`]: shade(base, 0.45),
    [`--${name}-soft`]: rgba(base, 0.14),
    [`--${name}-glow`]: rgba(base, 0.42),
    [`--${name}-line`]: rgba(base, 0.3),
    [`--on-${name}`]: textOn(base),
  };
}

/** Staff app: the platform owner picks the main colour and the sidebar colour per agency. */
export function dashboardVars(primary?: string, sidebar?: string): Record<string, string> {
  const p = forDark(primary && VALID.test(primary) ? primary : GHANJAH.cyan);
  const s = sidebar && VALID.test(sidebar) ? sidebar : "#0f0e0d";
  return {
    ...actionVars("brand", p),
    "--sidebar": s,
    "--bg-sidebar": s,
    "--sidebar-text": textOn(s),
  };
}

/** Customer page: the agency's main and accent colours (Oman magenta stays for the human team). */
export function storefrontVars(primary?: string, accent?: string): Record<string, string> {
  const raw = primary && VALID.test(primary) ? primary : GHANJAH.cyan;
  const p = forDark(raw);
  const a = forDark(accent && VALID.test(accent) ? accent : GHANJAH.cyanOnDark, 4.5);
  return {
    ...actionVars("brand", p),
    ...actionVars("agency-accent", a),
    "--brand-deep": shade(raw, -0.55),
  };
}
