import { CSSProperties, useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { get } from "../api";
import { GhanjahMark } from "../components/Brand";
import { Binoculars, SunHorizon } from "../components/Icon";
import { Modal } from "../components/ui";
import type { Block, StoreCtx } from "../components/storefront/context";
import { PhoneLayout } from "../components/storefront/PhoneLayout";
import { matchesBudget, matchesCategory, matchesQuery, usefulCategories, waLink } from "../components/storefront/shared";
import { useChat } from "../components/storefront/useChat";
import { WebLayout } from "../components/storefront/WebLayout";
import { STOREFRONT_TEXT, useLang } from "../i18n";
import type { Lang } from "../components/Money";
import { storefrontVars } from "../theme";
import type { PublicCompany, TravelPackage } from "../types";

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

  useEffect(() => {
    setCompany(null);
    setNotFound(false);
    get<PublicCompany>(`/api/public/companies/${slug}`).then((c) => {
      setCompany(c);
      document.title = c.name;
    }).catch(() => setNotFound(true));
    get<TravelPackage[]>(`/api/public/companies/${slug}/packages`).then(setPackages).catch(() => {});
  }, [slug]);

  // The customer page has its own dark background (the staff app's is a little darker).
  useEffect(() => {
    document.body.classList.add("sf-body");
    return () => document.body.classList.remove("sf-body");
  }, []);

  const dir = lang === "ar" ? "rtl" : "ltr";
  if (notFound || !company) {
    return (
      <div className="sf sf-state" dir={dir} lang={lang}>
        <div className="sf-orbs" aria-hidden="true" />
        {notFound ? (
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

function StorefrontPage({ slug, company, packages, lang, setLang }: {
  slug: string; company: PublicCompany; packages: TravelPackage[]; lang: Lang; setLang: (l: Lang) => void;
}) {
  const t = STOREFRONT_TEXT[lang];
  const desktop = useMediaQuery(DESKTOP);
  const b = company.branding;
  const agent = company.ai_agent_name || "Sara";

  const [query, setQuery] = useState("");
  const [budget, setBudget] = useState("");
  const [catState, setCat] = useState(0);
  const [pkg, setPkg] = useState<TravelPackage | null>(null);
  const [pkgOnTop, setPkgOnTop] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [confirmNew, setConfirmNew] = useState(false);

  const chat = useChat({ slug, company, lang, t, active: desktop || chatOpen });

  const cats = useMemo(() => usefulCategories(packages), [packages]);
  const cat = cats.includes(catState) ? catState : 0;
  const shown = packages.filter((p) => matchesQuery(p, query) && matchesBudget(p, budget) && matchesCategory(p, cat));
  const filtering = !!(query.trim() || budget.trim() || cat);

  // Page order from the agency's settings ("search" always sits at the top);
  // "How booking works" follows the trips.
  const blocks = useMemo(() => {
    const out: Block[] = [];
    for (const s of b.sections) {
      if ((s === "featured" || s === "offers") && !out.includes(s)) out.push(s);
      else if ((s === "about" || s === "contact") && !out.includes("about")) out.push("about");
    }
    const lastTrips = Math.max(out.indexOf("featured"), out.indexOf("offers"));
    out.splice(lastTrips + 1, 0, "how");
    return out;
  }, [b.sections]);

  const aboutText = pick(lang, b.about_en, b.about_ar);
  const about = b.sections.includes("about") && aboutText
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
    openPackage, book, openChat, askNew,
  };

  const style = {
    ...storefrontVars(b.primary_color, b.accent_color),
  } as CSSProperties;

  return (
    <div className={`sf sf-hero-${b.hero_style} ${b.card_style === "square" ? "sf-square" : ""} ${desktop ? "sf-is-web" : "sf-is-phone"}`}
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
