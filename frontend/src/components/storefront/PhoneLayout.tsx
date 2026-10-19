import { ReactNode, RefObject, useEffect, useRef, useState } from "react";
import { ArrowRight, MagnifyingGlass, SlidersHorizontal, WhatsappLogo } from "../Icon";
import { OmrSign } from "../Money";
import type { TravelPackage } from "../../types";
import { ChatHeader, ChatView } from "./ChatView";
import type { StoreCtx } from "./context";
import { PhonePackage } from "./PackageDetails";
import { AboutBlock, AgencyMark, CategoryChips, HowSteps, PoweredBy, TripsEmpty } from "./Sections";
import { FeaturedPoster, OfferRow, PhotoCard } from "./TripCards";

/** Open screens, most recent last: Escape closes only the top one. */
const openScreens: symbol[] = [];

/** A full-screen layer pushed in from the inline end (mirrored in Arabic). It stays mounted while
 *  closed so it can slide out, and keeps its state (the chat keeps its draft and scroll). */
function PushScreen({ open, onClose, label, className = "", focusRef, children }: {
  open: boolean; onClose: () => void; label: string; className?: string;
  focusRef?: RefObject<HTMLElement>; children: ReactNode;
}) {
  const box = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement as HTMLElement | null;
    const me = Symbol("screen");
    openScreens.push(me);
    // Focus after the push has started (focusing an off-screen element would scroll it).
    const id = window.setTimeout(() => {
      (focusRef?.current ?? box.current?.querySelector<HTMLElement>("button, input"))?.focus({ preventScroll: true });
    }, 60);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && openScreens[openScreens.length - 1] === me && !document.querySelector(".modal-backdrop")) close.current();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(id);
      window.removeEventListener("keydown", onKey);
      openScreens.splice(openScreens.indexOf(me), 1);
      const prev = opener.current;
      if (prev && document.contains(prev) && prev.offsetParent !== null) prev.focus({ preventScroll: true });
    };
  }, [open, focusRef]);

  useEffect(() => { if (box.current) box.current.inert = !open; }, [open]);

  return (
    <div ref={box} className={`sf-screen ${open ? "sf-open" : ""} ${className}`} role="dialog" aria-modal={open} aria-label={label} aria-hidden={!open}>
      {children}
    </div>
  );
}

export function PhoneLayout({ ctx, pkg, pkgOnTop, closePackage, chatOpen, closeChat, heroBg }: {
  ctx: StoreCtx;
  pkg: TravelPackage | null;
  pkgOnTop: boolean;
  closePackage: () => void;
  chatOpen: boolean;
  closeChat: () => void;
  heroBg: string | null;
}) {
  const { t, lang, company, agent, chat } = ctx;
  const home = useRef<HTMLDivElement>(null);
  const chatInput = useRef<HTMLInputElement>(null);
  const [lastPkg, setLastPkg] = useState<TravelPackage | null>(pkg);
  const [budgetOpen, setBudgetOpen] = useState(!!ctx.budget);
  useEffect(() => { if (pkg) setLastPkg(pkg); }, [pkg]);
  useEffect(() => { if (home.current) home.current.inert = !!pkg || chatOpen; }, [pkg, chatOpen]);

  const custom = ctx.heroTitle;
  const showFeatured = !ctx.filtering && ctx.featured.length > 0;

  const { cards, el } = ctx;
  const row = (p: TravelPackage) => cards.style === "photo"
    ? <PhotoCard key={p.id} p={p} t={t} lang={lang} cards={cards} agent={agent} phone onOpen={() => ctx.openPackage(p)} onBook={() => ctx.book(p)} />
    : <OfferRow key={p.id} p={p} t={t} lang={lang} cards={cards} onOpen={() => ctx.openPackage(p)} onBook={() => ctx.book(p)} />;

  const blocks = ctx.blocks.map((b) => {
    if (b === "featured") {
      if (!showFeatured) return null;
      return cards.style === "compact" ? (
        <section key="featured" className="sf-p-offers sf-p-featured-list" aria-labelledby="sf-feat-title">
          <div className="sf-p-offers-head"><h2 id="sf-feat-title">{t.featuredTitle}</h2></div>
          <div className={`sf-offer-list ${company.branding.card_style === "square" ? "sf-square" : ""}`}>{ctx.featured.map(row)}</div>
        </section>
      ) : (
        <section key="featured" className="sf-p-featured" aria-label={t.featuredTitle}>
          <div className={`sf-carousel ${cards.style === "photo" ? "sf-photo-carousel" : ""}`}>
            {ctx.featured.map((p) => cards.style === "photo" ? row(p)
              : <FeaturedPoster key={p.id} p={p} t={t} lang={lang} cards={cards} onOpen={() => ctx.openPackage(p)} />)}
          </div>
        </section>
      );
    }
    if (b === "offers") {
      return (
        <section key="offers" id="trips" className="sf-p-offers" aria-labelledby="sf-offers-title">
          <div className="sf-p-offers-head">
            <h2 id="sf-offers-title">{t.offers}</h2>
            {el.offers_count && ctx.packages.length > 0 && <span className="sf-count">{t.count(ctx.shown.length, ctx.packages.length)}</span>}
          </div>
          {ctx.shown.length === 0 ? <TripsEmpty ctx={ctx} /> : (
            <div className={`sf-offer-list ${cards.style === "photo" ? "sf-photo-list" : ""} ${company.branding.card_style === "square" ? "sf-square" : ""}`}>
              {ctx.shown.map(row)}
            </div>
          )}
          {el.prices_note && company.currency === "OMR" && ctx.shown.length > 0 && <p className="sf-note">{t.pricesNote}</p>}
        </section>
      );
    }
    if (b === "how") return <HowSteps key="how" ctx={ctx} />;
    return <AboutBlock key="about" ctx={ctx} />;
  });

  return (
    <div className="sf-phone">
      <div ref={home} className="sf-home">
        <div className="sf-home-scroll">
          <div className={`sf-p-top ${heroBg ? "sf-has-photo" : ""}`} style={heroBg ? { backgroundImage: heroBg } : undefined}>
            <header className="sf-p-header">
              <AgencyMark ctx={ctx} />
              <span className="sf-p-name">{company.name}</span>
              {el.lang_switch && <button type="button" className="sf-lang" onClick={ctx.toggleLang} lang={lang === "ar" ? "en" : "ar"}>{t.switchTo}</button>}
              {el.whatsapp_icon && ctx.whatsapp && (
                <a className="sf-wa-icon" href={ctx.whatsapp} target="_blank" rel="noreferrer" aria-label={t.whatsapp}><WhatsappLogo weight="fill" /></a>
              )}
            </header>
            <div className="sf-p-hero">
              {el.kicker && <div className="sf-kicker-online"><span className="sf-online-dot" />{t.online(agent)}</div>}
              <h1 className="sf-p-title" dir="auto">
                {custom ?? <>{t.heroA} <em className="sf-accent">{t.heroB}</em></>}
              </h1>
              {ctx.heroText && <p className="sf-p-lead" dir="auto">{ctx.heroText}</p>}
              {ctx.showSearch && <div className="sf-p-search">
                <MagnifyingGlass className="sf-p-search-icon" aria-hidden="true" />
                <input type="search" value={ctx.query} onChange={(e) => ctx.setQuery(e.target.value)}
                  placeholder={t.searchPlaceholder} aria-label={t.searchLabel} enterKeyHint="search" />
                {el.budget_filter && <button type="button" className={`sf-p-filter ${budgetOpen ? "sf-open" : ""} ${ctx.budget ? "sf-set" : ""}`}
                  aria-expanded={budgetOpen} aria-controls="sf-budget" aria-label={t.budgetLabel} title={t.budgetToggle}
                  onClick={() => setBudgetOpen((o) => !o)}>
                  <SlidersHorizontal />
                </button>}
              </div>}
              {ctx.showSearch && el.budget_filter && budgetOpen && (
                <label className="sf-p-budget anim-in" id="sf-budget">
                  {company.currency === "OMR" ? <OmrSign /> : <span className="sf-cur">{company.currency}</span>}
                  <input type="number" min={0} inputMode="decimal" value={ctx.budget} onChange={(e) => ctx.setBudget(e.target.value)}
                    placeholder={t.budgetPlaceholder} aria-label={t.budgetLabel} />
                </label>
              )}
            </div>
          </div>
          <CategoryChips ctx={ctx} className="sf-p-chips" />
          {blocks}
          <footer className="sf-p-footer">
            <PoweredBy ctx={ctx} />
            {el.powered_by && el.footer_note && <span aria-hidden="true">·</span>}
            {el.footer_note && <span>{t.footer}</span>}
          </footer>
        </div>
        {el.chat_launcher && <div className="sf-dock">
          <button type="button" className="sf-dock-btn" onClick={ctx.openChat}>
            <span className="sf-dock-avatar" aria-hidden="true">{agent.trim().charAt(0).toUpperCase()}</span>
            <span className="sf-dock-text"><strong>{t.chatWith(agent)}</strong><span>{t.chatButtonSub}</span></span>
            <ArrowRight className="flip sf-dock-arrow" aria-hidden="true" />
          </button>
        </div>}
      </div>

      <PushScreen open={!!pkg} onClose={closePackage} label={lastPkg ? t.openPackage(lastPkg.title) : t.back}
        className={`sf-pkg-screen ${pkgOnTop ? "sf-top" : ""}`}>
        {lastPkg && <PhonePackage p={lastPkg} t={t} lang={lang} agent={agent} onBack={closePackage} onBook={() => ctx.book(lastPkg)} />}
      </PushScreen>

      <PushScreen open={chatOpen} onClose={closeChat} label={t.chatWith(agent)} className="sf-chat-screen" focusRef={chatInput}>
        <ChatHeader company={company} chat={chat} t={t} onClose={closeChat} onNew={ctx.askNew} />
        <ChatView chat={chat} t={t} lang={lang} packages={ctx.packages} onViewPackage={ctx.openPackage}
          inputRef={chatInput} live={chatOpen} onFocus={chat.ensure} />
      </PushScreen>
    </div>
  );
}
