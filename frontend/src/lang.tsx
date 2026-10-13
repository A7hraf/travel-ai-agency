import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import type { Lang } from "./components/Money";
import { AR, AR_PATTERNS, AR_PLURALS } from "./locales/ar";

const STORAGE_KEY = "travel_lang";

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "ar" || saved === "en") return saved;
  } catch {
    /* storage unavailable */
  }
  return navigator.language?.toLowerCase().startsWith("ar") ? "ar" : "en";
}

let currentLang: Lang = initialLang();

/** Translate an English text (the key) into the current language; {name} placeholders are filled in. */
export function tr(text: string, vars?: Record<string, string | number>): string {
  let out = currentLang === "ar" ? AR[text] ?? text : text;
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(String(v));
  return out;
}

export const TICKET_STATUS_LABELS: Record<string, string> = {
  pending_payment: "Waiting for payment",
  in_progress: "In progress",
  paid: "Paid",
  confirmed: "Confirmed",
  cancelled: "Cancelled",
};

/** "1 adult" / "2 adults" in English; Arabic uses its own singular, dual, plural forms (see AR_PLURALS). */
export function plural(n: number, one: string, other: string): string {
  if (currentLang === "ar") {
    const forms = AR_PLURALS[other];
    if (forms) {
      const category = new Intl.PluralRules("ar").select(n) as keyof typeof forms;
      return (forms[category] ?? forms.other).split("{n}").join(String(n));
    }
  }
  return tr(n === 1 ? one : other, { n });
}

// English server texts made a little friendlier (raw status values -> labels).
const EN_PATTERNS: [RegExp, string][] = [
  [/^Ticket (\S+): (\w+) → (\w+) by (.+)$/, "Ticket {1}: {2:status} → {3:status} by {4}"],
  [/^A booking can't go from (\w+) to (\w+)$/, "A booking can't go from {1:status} to {2:status}"],
];

function fill(template: string, groups: string[]): string {
  return template.replace(/\{(\d)(?::(\w+))?\}/g, (_, i: string, mode?: string) => {
    const v = groups[Number(i)] ?? "";
    if (mode === "t") return trServer(v);
    if (mode === "status") return TICKET_STATUS_LABELS[v] ? tr(TICKET_STATUS_LABELS[v]) : v;
    if (mode === "adults") return plural(Number(v), "{n} adult", "{n} adults");
    if (mode === "children") return plural(Number(v), "{n} child", "{n} children");
    return v;
  });
}

/**
 * Translates a text written by the server (error messages, chat events, handover reasons).
 * Fixed texts come from the AR dictionary; texts with names or numbers in them from AR_PATTERNS.
 * Unknown texts (e.g. a reason the AI wrote) are shown as they are.
 */
export function trServer(text: string | null | undefined): string {
  if (!text) return text ?? "";
  const s = text.trim();
  const patterns = currentLang === "ar" ? AR_PATTERNS : EN_PATTERNS;
  if (currentLang === "ar" && AR[s]) return AR[s];
  for (const [re, template] of patterns) {
    const m = s.match(re);
    if (m) return fill(template, m);
  }
  return text;
}

export function currentLocale(): string {
  return currentLang === "ar" ? "ar-OM-u-nu-latn" : "en-GB";
}

interface LangState {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: typeof tr;
}

const LangContext = createContext<LangState>({ lang: currentLang, setLang: () => {}, t: tr });

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(currentLang);
  const setLang = useCallback((next: Lang) => {
    currentLang = next;
    setLangState(next);
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch {
      /* storage unavailable */
    }
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);
  // `t` changes identity with the language so components using it re-render.
  const t = useCallback((text: string, vars?: Record<string, string | number>) => tr(text, vars), [lang]); // eslint-disable-line react-hooks/exhaustive-deps
  return <LangContext.Provider value={{ lang, setLang, t }}>{children}</LangContext.Provider>;
}

export function useI18n(): LangState {
  return useContext(LangContext);
}

/** [language, setter] — kept for the customer page. */
export function useLang(): [Lang, (lang: Lang) => void] {
  const { lang, setLang } = useI18n();
  return [lang, setLang];
}

/** Button that switches between English and Arabic. */
export function LangSwitch({ className = "btn btn-sm" }: { className?: string }) {
  const { lang, setLang } = useI18n();
  return (
    <button type="button" className={className} onClick={() => setLang(lang === "ar" ? "en" : "ar")}>
      {lang === "ar" ? "English" : "العربية"}
    </button>
  );
}
