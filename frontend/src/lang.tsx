import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import type { Lang } from "./components/Money";
import { AR } from "./locales/ar";

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
