import { CSSProperties, useCallback, useEffect, useMemo, useState } from "react";
import { pinTheme } from "../themeMode";
import { useParams } from "react-router-dom";
import { ApiError, get } from "../api";
import { tr } from "../lang";
import { GhanjahMark } from "../components/Brand";
import { Binoculars, SunHorizon } from "../components/Icon";
import { Modal } from "../components/ui";
import type { Block, StoreCtx } from "../components/storefront/context";
import { PhoneLayout } from "../components/storefront/PhoneLayout";
import { STORY_KEYS, storyHasContent } from "../components/storefront/Stories";
import { matchesBudget, matchesCategory, matchesQuery, usefulCategories, waLink } from "../components/storefront/shared";
import { DEFAULT_CARDS, DEFAULT_ELEMENTS, pageVars } from "../components/storefront/style";
import { applyTexts } from "../components/storefront/texts";
import { useChat } from "../components/storefront/useChat";
import { WebLayout } from "../components/storefront/WebLayout";
import { STOREFRONT_TEXT, useLang } from "../i18n";
import type { Lang } from "../components/Money";
import type { PublicCompany, StoryKey, TravelPackage } from "../types";

const DESKTOP = "(min-width: 901px)";

function useMediaQuery(query: string): boolean {
  const [match, setMatch] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatch(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return match;
}

/** Text in the visitor's language, falling back to the other language. */
const pick = (lang: Lang, en: string, ar: string) => ((lang === "ar" ? ar || en : en || ar) || "").trim();

export default function Storefront() {
  const { slug = "" } = useParams();
  const [lang, setLang] = useLang();
  const t = STOREFRONT_TEXT[lang];
  const [company, setCompany] = useState<PublicCompany | null>(null);
  const [packages, setPackages] = useState<TravelPackage[]>([]);
  const [notFound, setNotFound] = useState(false);
  // Anything but "no such company" (server error, no connection): say so and offer to try again.
  const [failed, setFailed] = useState(false);
  // The agency's subscription ended (after its grace period): the page is paused, nothing is deleted.
  const [paused, setPaused] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setCompany(null);
    setNotFound(false);
    setFailed(false);
    setPaused(false);
    get<PublicCompany>(`/api/public/companies/${slug}`).then((c) => {
      setCompany(c);
      document.title = c.name;
    }).catch((e) => (e instanceof ApiError && e.status === 423 ? setPaused(true)
      : e instanceof ApiError && e.status === 404 ? setNotFound(true) : setFailed(true)));
    get<TravelPackage[]>(`/api/public/companies/${slug}/packages`).then(setPackages)
      .catch((e) => { if (!(e instanceof ApiError && (e.status === 404 || e.status === 423))) setFailed(true); });
  }, [slug, attempt]);

  // The customer page has its own dark background (the staff app's is a little darker).
  useEffect(() => {
    document.body.classList.add("sf-body");
    // The customer page has the agency's own design: it does not follow the team's light/dark choice.
    const unpin = pinTheme("dark");
    return () => {
      document.body.classList.remove("sf-body");
      unpin();
    };
  }, []);

  const dir = lang === "ar" ? "rtl" : "ltr";
  if (notFound || failed || paused || !company) {
    return (
      <div className="sf sf-state" dir={dir} lang={lang}>
        <div className="sf-orbs" aria-hidden="true" />
        {paused ? (
          <div className="sf-state-box" role="status">
            <SunHorizon className="sf-empty-icon" />
            <h1>{t.paused}</h1>
            <p>{t.pausedHint}</p>
          </div>
        ) : failed && !notFound ? (
          <div className="sf-state-box" role="alert">
            <Binoculars className="sf-empty-icon" />
            <h1>{tr("This page could not be loaded")}</h1>
            <p>{tr("Check your internet connection and try again in a moment.")}</p>
            <button type="button" className="btn btn-primary" onClick={() => setAttempt((n) => n + 1)}>{tr("Try again")}</button>
          </div>
        ) : notFound ? (
          <div className="sf-state-box" role="alert">
            <Binoculars className="sf-empty-icon" />
            <h1>{t.notFound}</h1>
            <p>{t.notFoundHint}</p>
            <a className="sf-powered" href="/"><GhanjahMark dark size={22} /><span>{t.poweredBy}</span></a>
          </div>
        ) : (
          <div className="sf-state-box" role="status">
            <span className="sf-sunmark sf-pulse" aria-hidden="true"><SunHorizon weight="fill" /></span>
            <p>{t.loading}</p>
          </div>
        )}
      </div>
    );
  }
  return <StorefrontPage slug={slug} company={company} packages={packages} lang={lang} setLang={setLang} />;
}

/** The customer page for a company. The page editor renders it too, as its live preview
 *  (`layout` forces the phone or computer design, `preview` keeps the chat offline). */
export function StorefrontPage({ slug, company, packages, lang, setLang, layout, preview = false }: {
  slug: string; company: PublicCompany; packages: TravelPackage[]; lang: Lang; setLang: (l: Lang) => void;
  layout?: "phone" | "web"; preview?: boolean;
}) {
  const b = company.branding;
  const t = useMemo(() => applyTexts(lang, b.texts), [lang, b.texts]);
  const wide = useMediaQuery(DESKTOP);
  const desktop = layout ? layout === "web" : wide;
  const agent = company.ai_agent_name || "Sara";
  const el = { ...DEFAULT_ELEMENTS, ...b.elements };
  const cards = { ...DEFAULT_CARDS, ...b.cards };

  const [query, setQuery] = useState("");
  const [budget, setBudget] = useState("");
  const [catState, setCat] = useState(0);
  const [pkg, setPkg] = useState<TravelPackage | null>(null);
  const [pkgOnTop, setPkgOnTop] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [confirmNew, setConfirmNew] = useState(false);

  const chat = useChat({ slug, company, lang, t, active: desktop || chatOpen, offline: preview });

  const cats = useMemo(() => (el.chips ? usefulCategories(packages) : [0]), [packages, el.chips]);
  const cat = cats.includes(catState) ? catState : 0;
  const shown = packages.filter((p) => matchesQuery(p, query) && matchesBudget(p, budget) && matchesCategory(p, cat));
  const filtering = !!(query.trim() || budget.trim() || cat);

  // Page order from the agency's settings ("search" always sits in the top banner).
  const blocks = useMemo(() => {
    const out: Block[] = [];
    for (const s of b.sections) {
      if ((s === "featured" || s === "offers" || s === "how") && !out.includes(s)) out.push(s);
      else if ((s === "about" || s === "contact") && !out.includes("about")) out.push("about");
      else if ((STORY_KEYS as string[]).includes(s) && storyHasContent(b.stories?.[s as StoryKey]) && !out.includes(s as Block)) out.push(s as Block);
    }
    return out;
  }, [b.sections, b.stories]);

  const aboutText = pick(lang, b.about_en, b.about_ar);
  const about = b.sections.includes("about") && (aboutText || b.about_image)
    ? { title: pick(lang, b.about_title_en, b.about_title_ar) || t.aboutTitle, text: aboutText }
    : null;
  const heroTitle = (lang === "ar" ? b.hero_title_ar : b.hero_title_en).trim() || null;
  const heroText = (lang === "ar" ? b.hero_text_ar : b.hero_text_en).trim() || null;
  const heroBg = b.hero_style === "image" && b.hero_image
    ? `linear-gradient(180deg, rgba(20,19,18,.55) 0%, rgba(20,19,18,.72) 55%, var(--sf-bg) 100%), url(${JSON.stringify(b.hero_image)})`
    : null;

  const openChat = useCallback(() => {
    setChatOpen(true);
    chat.ensure();
  }, [chat]);

  const openPackage = useCallback((p: TravelPackage) => {
    setPkgOnTop(chatOpen);
    setPkg(p);
  }, [chatOpen]);

  const book = useCallback((p: TravelPackage) => {
    setPkg(null);
    setChatOpen(true);
    chat.send(t.interested(p.title, p.duration_days));
  }, [chat, t]);

  const ask = useCallback((message: string) => {
    setChatOpen(true);
    chat.send(message);
  }, [chat]);

  const askNew = useCallback(() => {
    if (chat.hasCustomer) setConfirmNew(true);
    else chat.restart();
  }, [chat]);

  const clearFilters = useCallback(() => { setQuery(""); setBudget(""); setCat(0); }, []);

  const ctx: StoreCtx = {
    slug, company, packages, t, lang, toggleLang: () => setLang(lang === "ar" ? "en" : "ar"), chat, agent,
    whatsapp: waLink(company.whatsapp_number),
    query, setQuery, budget, setBudget, cat, setCat, cats, shown,
    featured: packages.filter((p) => p.is_featured), filtering, clearFilters,
    blocks, heroTitle, heroText, about, showContact: b.sections.includes("contact"),
    showSearch: b.sections.includes("search"), el, cards,
    openPackage, book, openChat, ask, askNew,
  };

  const style = pageVars(b) as CSSProperties;

  return (
    <div className={`sf sf-hero-${b.hero_style} ${b.card_style === "square" ? "sf-square" : ""} ${desktop ? "sf-is-web" : "sf-is-phone"} sf-cards-${cards.style} ${preview ? "sf-preview" : ""}`}
      dir={lang === "ar" ? "rtl" : "ltr"} lang={lang} style={style}>
      <div className="sf-orbs" aria-hidden="true" />
      {desktop ? (
        <WebLayout ctx={ctx} pkg={pkg} closePackage={() => setPkg(null)} widgetOpen={chatOpen}
          closeWidget={() => setChatOpen(false)} heroBg={heroBg} />
      ) : (
        <PhoneLayout ctx={ctx} pkg={pkg} pkgOnTop={pkgOnTop} closePackage={() => setPkg(null)} chatOpen={chatOpen}
          closeChat={() => setChatOpen(false)} heroBg={heroBg} />
      )}
      {confirmNew && (
        <Modal title={t.newChat} onClose={() => setConfirmNew(false)}>
          <div className="sf-confirm" dir={lang === "ar" ? "rtl" : "ltr"}>
            <p>{t.newChatQ}</p>
            <div className="modal-actions">
              <span className="spacer" />
              <button type="button" className="btn" onClick={() => setConfirmNew(false)}>{t.cancel}</button>
              <button type="button" className="btn btn-primary" onClick={() => { setConfirmNew(false); chat.restart(); }}>{t.start}</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
