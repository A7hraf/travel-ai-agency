import { KeyboardEvent } from "react";
import type { TravelPackage } from "../../types";

/** Trip-type chips (All / Honeymoon / Family / Beach / City / Umrah). A chip matches a package when one
 *  of these words appears in its tags, title, place or description, in English or Arabic. */
const CATEGORY_WORDS: RegExp[] = [
  /.^/, // "All"
  /(^|[^\p{L}])(honeymoon|honey-moon|شهر عسل|عرسان)/iu,
  /(^|[^\p{L}])(famil|kids|عائل|العائل|أسر|الأسر)/iu,
  /(^|[^\p{L}])(beach|island|شاطئ|شواطئ|الشاطئ|الشواطئ)/iu,
  /(^|[^\p{L}])(city|cities|city-break|مدينة|مدن)([^\p{L}]|$)/iu,
  /(^|[^\p{L}])(umrah|omrah|عمرة|العمرة)/iu,
];

function haystack(p: TravelPackage): string {
  return [p.title, p.destination, p.country, p.tags.join(" "), p.description].join(" ").toLowerCase();
}

export function matchesCategory(p: TravelPackage, cat: number): boolean {
  return cat === 0 || CATEGORY_WORDS[cat].test(haystack(p));
}

export function matchesQuery(p: TravelPackage, query: string): boolean {
  const q = query.trim().toLowerCase();
  return !q || haystack(p).includes(q);
}

export function matchesBudget(p: TravelPackage, budget: string): boolean {
  const max = Number(budget);
  return !budget.trim() || !Number.isFinite(max) || max <= 0 || p.price_per_person <= max;
}

/** Categories that match at least one package (always "All" first). */
export function usefulCategories(packages: TravelPackage[]): number[] {
  return CATEGORY_WORDS.map((_, i) => i).filter((i) => i === 0 || packages.some((p) => matchesCategory(p, i)));
}

export const stars = (n: number | null) => (n ? "★".repeat(Math.max(0, Math.min(5, n))) : "");

/** Enter / Space opens a clickable card (cards are not buttons because they contain buttons). */
export function onCardKey(open: () => void) {
  return (e: KeyboardEvent) => {
    if ((e.key === "Enter" || e.key === " ") && e.target === e.currentTarget) {
      e.preventDefault();
      open();
    }
  };
}

/** Local date as YYYY-MM-DD. */
export function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export const waLink = (number: string | null | undefined) => {
  const digits = number?.replace(/\D/g, "");
  return digits ? `https://wa.me/${digits}` : null;
};

export const telLink = (phone: string) => `tel:${phone.replace(/[^\d+]/g, "")}`;
