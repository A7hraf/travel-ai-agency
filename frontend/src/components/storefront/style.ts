/** CSS variables of the customer page from the agency's colours (shared by the page and the editor preview). */
import { isDark, shade, storefrontVars, textOn } from "../../theme";
import type { CardDesign, PageElements, PublicBranding } from "../../types";

const HEX = /^#[0-9a-fA-F]{6}$/;
const ok = (v: string | null | undefined): v is string => !!v && HEX.test(v);

function rgba(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

export function pageVars(b: Pick<PublicBranding, "primary_color" | "accent_color" | "bg_color" | "surface_color" | "text_color" | "highlight_color">): Record<string, string> {
  const vars = storefrontVars(b.primary_color, b.accent_color);
  const lightPage = ok(b.bg_color) && !isDark(b.bg_color);
  if (lightPage && ok(b.primary_color)) {
    // On a light background the brand colour is used as chosen (it is only lightened for dark pages).
    const p = b.primary_color;
    Object.assign(vars, {
      "--brand": p, "--brand-hover": shade(p, -0.18), "--brand-soft": rgba(p, 0.12),
      "--brand-glow": rgba(p, 0.35), "--brand-line": rgba(p, 0.3), "--on-brand": textOn(p),
    });
  }
  if (ok(b.bg_color)) vars["--sf-bg"] = b.bg_color;
  const text = ok(b.text_color) ? b.text_color : lightPage ? "#201e1d" : null;
  if (text) {
    vars["--sf-text"] = text;
    vars["--text"] = text;
    vars["--sf-hair"] = rgba(text, 0.12);
  }
  if (ok(b.surface_color)) {
    vars["--sf-surface"] = b.surface_color;
    vars["--sf-surface-2"] = b.surface_color;
    vars["--sf-card"] = b.surface_color;
  }
  if (ok(b.highlight_color)) {
    vars["--accent"] = b.highlight_color;
    vars["--accent-soft"] = rgba(b.highlight_color, 0.15);
  }
  return vars;
}

/** WCAG contrast ratio of two #rrggbb colours. */
export function contrastRatio(a: string, b: string): number {
  const lum = (hex: string) => {
    const n = parseInt(hex.slice(1), 16);
    const [r, g, bl] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
      const s = c / 255;
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}


export const DEFAULT_ELEMENTS: PageElements = {
  kicker: true, trust: true, lang_switch: true, nav_links: true, nav_phone: true, whatsapp_icon: true,
  budget_filter: true, chips: true, hero_chat: true, chat_launcher: true, offers_count: true,
  prices_note: true, footer_note: true, powered_by: true,
};

export const DEFAULT_CARDS: CardDesign = {
  style: "poster", columns: 3, show_price: true, show_duration: true, show_hotel: false,
  show_next_date: false, show_seats: false, show_tags: false, per_person: false, show_button: true,
};
