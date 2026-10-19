import { FormEvent, useEffect, useRef, useState } from "react";
import { Clock, Headset, MagnifyingGlass, ShieldCheck, Sparkle } from "../Icon";
import { OmrSign } from "../Money";
import { Modal } from "../ui";
import type { TravelPackage } from "../../types";
import { ChatAvatar, ChatHeader, ChatTitle, ChatView } from "./ChatView";
import type { StoreCtx } from "./context";
import { WebPackage } from "./PackageDetails";
import { AboutBlock, AgencyMark, CategoryChips, HowSteps, PoweredBy, TripsEmpty } from "./Sections";
import { telLink } from "./shared";
import { PhotoCard, WebPoster, WebRow } from "./TripCards";

export function WebLayout({ ctx, pkg, closePackage, widgetOpen, closeWidget, heroBg }: {
  ctx: StoreCtx;
  pkg: TravelPackage | null;
  closePackage: () => void;
  widgetOpen: boolean;
  closeWidget: () => void;
  heroBg: string | null;
}) {
  const { t, lang, company, agent, chat } = ctx;
  const b = company.branding;
  const widgetInput = useRef<HTMLInputElement>(null);
  const launcher = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);
  const heroChat = useRef<HTMLDivElement>(null);
  const [heroInView, setHeroVisible] = useState(true);
  const { el, cards } = ctx;
  const heroVisible = el.hero_chat && heroInView;

  // The launcher is not needed while the live chat in the hero is on screen.
  useEffect(() => {
    const el = heroChat.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([e]) => setHeroVisible(e.isIntersecting), { threshold: 0.25 });
    io.observe(el);
    return () => io.disconnect();
  }, [el.hero_chat]);

  // Focus the widget's message box when it opens; back to the launcher when it closes.
  useEffect(() => {
    if (widgetOpen) widgetInput.current?.focus({ preventScroll: true });
    else if (wasOpen.current) {
      const back = launcher.current?.classList.contains("sf-away") ? heroChat.current?.querySelector("input") : launcher.current;
      back?.focus({ preventScroll: true });
    }
    wasOpen.current = widgetOpen;
  }, [widgetOpen]);
  useEffect(() => {
    if (!widgetOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !document.querySelector(".modal-backdrop")) closeWidget(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [widgetOpen, closeWidget]);

  const findTrips = (e: FormEvent) => {
    e.preventDefault();
    document.getElementById("trips")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const custom = ctx.heroTitle;
  const hasTrips = ctx.blocks.includes("featured") || ctx.blocks.includes("offers");
  const hasAbout = ctx.blocks.includes("about") && (!!ctx.about || ctx.showContact);
  const gridClass = `sf-wgrid sf-cols-${cards.columns} ${cards.style === "compact" ? "sf-list" : ""} ${cards.style === "photo" ? "sf-photo-grid" : ""} ${b.card_style === "square" ? "sf-square" : ""}`;

  const trips = (title: string, list: TravelPackage[]) => (
    <section key="trips" id="trips" className="sf-wtrips" aria-labelledby="sf-trips-title">
      <div className="sf-wtrips-head">
        <h2 id="sf-trips-title">{title}</h2>
        <CategoryChips ctx={ctx} />
      </div>
      {list.length === 0 ? <TripsEmpty ctx={ctx} /> : (
        <div className={gridClass}>
          {list.map((p) => cards.style === "compact"
            ? <WebRow key={p.id} p={p} t={t} lang={lang} cards={cards} agent={agent} onOpen={() => ctx.openPackage(p)} onBook={() => ctx.book(p)} />
            : cards.style === "photo"
              ? <PhotoCard key={p.id} p={p} t={t} lang={lang} cards={cards} agent={agent} onOpen={() => ctx.openPackage(p)} onBook={() => ctx.book(p)} />
              : <WebPoster key={p.id} p={p} t={t} lang={lang} cards={cards} onOpen={() => ctx.openPackage(p)} />)}
        </div>
      )}
      {el.prices_note && company.currency === "OMR" && list.length > 0 && <p className="sf-note">{t.pricesNote}</p>}
    </section>
  );

  // "featured" and "offers" become one "Trips on sale" grid (featured first, as the server sorts them);
  // with only "featured" visible, the grid shows the featured trips.
  let tripsDone = false;
  const blocks = ctx.blocks.map((blk) => {
    if (blk === "featured" || blk === "offers") {
      if (tripsDone) return null;
      tripsDone = true;
      const onlyFeatured = !ctx.blocks.includes("offers");
      return onlyFeatured
        ? trips(t.featuredTitle, ctx.filtering ? ctx.shown.filter((p) => p.is_featured) : ctx.featured)
        : trips(t.tripsOnSale, ctx.shown);
    }
    if (blk === "how") return <HowSteps key="how" ctx={ctx} />;
    return <AboutBlock key="about" ctx={ctx} />;
  });

  return (
    <div className="sf-web">
      <div className={`sf-wtop ${heroBg ? "sf-has-photo" : ""}`} style={heroBg ? { backgroundImage: heroBg } : undefined}>
        <div className="sf-wtop-glow" aria-hidden="true" />
        <nav className="sf-wnav" aria-label={company.name}>
          <a className="sf-wbrand" href="#top" onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
            <AgencyMark ctx={ctx} size={42} /><span>{company.name}</span>
          </a>
          {el.nav_links && hasTrips && <a className="sf-wlink" href="#trips">{t.navTrips}</a>}
          {el.nav_links && ctx.blocks.includes("how") && <a className="sf-wlink" href="#how">{t.navHow}</a>}
          {el.nav_links && hasAbout && <a className="sf-wlink" href="#about">{t.navAbout}</a>}
          {el.nav_phone && company.contact_phone && <a className="sf-wphone" href={telLink(company.contact_phone)}><bdi dir="ltr">{company.contact_phone}</bdi></a>}
          {el.lang_switch && <button type="button" className="sf-lang" onClick={ctx.toggleLang} lang={lang === "ar" ? "en" : "ar"}>{t.switchTo}</button>}
          <button type="button" className="sf-cta sf-sm" onClick={ctx.openChat}><Sparkle />{t.chatWith(agent)}</button>
        </nav>

        <div className={`sf-whero ${el.hero_chat ? "" : "sf-no-chat"}`}>
          <div className="sf-whero-text">
            {el.kicker && <div className="sf-kicker-cyan sf-kicker-magenta-dot">{t.fromOman}</div>}
            <h1 className={`sf-wtitle ${custom && custom.length > 26 ? "sf-long" : ""}`} dir="auto">
              {custom ?? <>{t.heroA}<br /><em className="sf-accent">{t.heroB}</em></>}
            </h1>
            <p className="sf-wlead" dir="auto">{ctx.heroText ?? t.webLead(agent)}</p>
            {ctx.showSearch && <form className="sf-wsearch" role="search" onSubmit={findTrips}>
              <MagnifyingGlass className="sf-wsearch-icon" aria-hidden="true" />
              <input className="q" type="search" value={ctx.query} onChange={(e) => ctx.setQuery(e.target.value)}
                placeholder={t.webSearchPlaceholder} aria-label={t.searchLabel} />
              {el.budget_filter && <>
                <span className="sf-wsearch-sep" aria-hidden="true" />
                {company.currency === "OMR" ? <OmrSign /> : <span className="sf-cur">{company.currency}</span>}
                <input className="b" type="number" min={0} inputMode="decimal" value={ctx.budget} onChange={(e) => ctx.setBudget(e.target.value)}
                  placeholder={t.webBudgetPlaceholder} aria-label={t.budgetLabel} />
              </>}
              <button type="submit" className="sf-wsearch-go">{t.findTrips}</button>
            </form>}
            {el.trust && <ul className="sf-trust">
              <li><Clock />{t.trust[0]}</li>
              <li><Headset />{t.trust[1]}</li>
              <li><ShieldCheck />{t.trust[2]}</li>
            </ul>}
          </div>

          {el.hero_chat && <div ref={heroChat} className="sf-herochat" aria-label={t.chatWith(agent)} role="region">
            <div className="sf-herochat-head">
              <ChatAvatar company={company} human={chat.human} size={44} />
              <ChatTitle company={company} human={chat.human} t={t} />
              <span className="sf-live"><span className="sf-live-dot" />{t.live}</span>
            </div>
            <ChatView chat={chat} t={t} lang={lang} packages={ctx.packages} onViewPackage={ctx.openPackage}
              live={!widgetOpen} size="sm" placeholder={t.askAnything(agent)} onFocus={chat.ensure} />
          </div>}
        </div>
      </div>

      <main className="sf-wmain">{blocks}</main>

      <footer className="sf-wfoot">
        <span className="sf-wfoot-name">{company.name}</span>
        {company.contact_email && <a href={`mailto:${company.contact_email}`}><bdi dir="ltr">{company.contact_email}</bdi></a>}
        <span className="sf-wfoot-note">{el.footer_note ? t.footer : ""}</span>
        <PoweredBy ctx={ctx} />
      </footer>

      {pkg && (
        <Modal title={pkg.title} onClose={closePackage} wide>
          <WebPackage p={pkg} t={t} lang={lang} agent={agent} onClose={closePackage} onBook={() => ctx.book(pkg)} />
        </Modal>
      )}

      {widgetOpen ? (
        <div className="sf-widget" role="dialog" aria-label={t.chatWith(agent)}>
          <ChatHeader company={company} chat={chat} t={t} onClose={closeWidget} onNew={ctx.askNew} compact />
          <ChatView chat={chat} t={t} lang={lang} packages={ctx.packages} onViewPackage={ctx.openPackage}
            inputRef={widgetInput} live size="sm" onFocus={chat.ensure} />
        </div>
      ) : el.chat_launcher && (
        <button ref={launcher} type="button" className={`sf-launcher ${heroVisible ? "sf-away" : ""}`} onClick={ctx.openChat}
          tabIndex={heroVisible ? -1 : undefined} aria-hidden={heroVisible || undefined}>
          <span className="sf-dock-avatar" aria-hidden="true">{agent.trim().charAt(0).toUpperCase()}</span>
          {t.chatWith(agent)}
        </button>
      )}
    </div>
  );
}
