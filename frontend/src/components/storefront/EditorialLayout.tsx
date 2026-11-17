import "@fontsource/cormorant-garamond/300.css";
import "@fontsource/cormorant-garamond/400.css";
import "@fontsource/cormorant-garamond/400-italic.css";
import "@fontsource/cormorant-garamond/500.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "../../styles/editorial.css";
import { type ReactNode, useEffect, useRef, useState } from "react";
import type { StorefrontText } from "../../i18n";
import { ArrowLeft, ArrowRight, Envelope, Phone, WhatsappLogo } from "../Icon";
import { Money } from "../Money";
import { Modal } from "../ui";
import type { StoryItem, StoryKey, StorySection, TravelPackage } from "../../types";
import { ChatHeader, ChatView } from "./ChatView";
import type { Block, StoreCtx } from "./context";
import { WebPackage } from "./PackageDetails";
import { PoweredBy } from "./Sections";
import { Emph, STORY_KEYS, plain, storyHasContent, storyNavLabel } from "./Stories";
import { telLink } from "./shared";

const pick = (lang: string, en: string, ar: string) => ((lang === "ar" ? ar || en : en || ar) || "").trim();
const num = (i: number) => String(i + 1).padStart(2, "0");
const AR = /[\u0600-\u06FF]/;
/** Direction of a text from its letters (dir="auto" would read "WE ARE ESCAPE …" in Arabic as left-to-right). */
const D = (text: string | null | undefined): "rtl" | "ltr" | "auto" => (!text ? "auto" : AR.test(text) ? "rtl" : "ltr");
const lines = (text: string) => text.split("\n").map((x) => x.replace(/^[-•·]\s*/, "").trim()).filter(Boolean);

/** The editorial customer page: a magazine-style design for both phones and computers. */
export function EditorialLayout({ ctx, desktop, pkg, closePackage, chatOpen, closeChat }: {
  ctx: StoreCtx; desktop: boolean; pkg: TravelPackage | null; closePackage: () => void; chatOpen: boolean; closeChat: () => void;
}) {
  const { t, lang, company, agent, chat, el } = ctx;
  const b = company.branding;
  const [scrolled, setScrolled] = useState(false);
  const [menu, setMenu] = useState(false);
  const chatInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 40);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  useEffect(() => { if (chatOpen) chatInput.current?.focus({ preventScroll: true }); }, [chatOpen]);
  useEffect(() => {
    if (!menu && !chatOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || document.querySelector(".modal-backdrop")) return;
      if (menu) setMenu(false); else closeChat();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menu, chatOpen, closeChat]);

  const tagline = pick(lang, b.tagline_en, b.tagline_ar);
  const plan = () => { setMenu(false); ctx.ask(t.edPlanMsg); };
  const story = (k: StoryKey): StorySection | undefined => b.stories?.[k];
  const tripsBlock = ctx.blocks.find((x) => x === "featured" || x === "offers");

  // Menu: the sections on the page, in order.
  const links = ctx.blocks.flatMap((x): { id: string; label: string }[] => {
    if ((STORY_KEYS as string[]).includes(x)) return [{ id: x, label: storyNavLabel(ctx, x as StoryKey) }];
    if (x === tripsBlock) return (ctx.blocks.includes("offers") ? ctx.packages : ctx.featured).length ? [{ id: "trips", label: t.navTrips }] : [];
    if (x === "how") return [{ id: "how", label: t.navHow }];
    if (x === "about" && (ctx.about || ctx.showContact)) return [{ id: "about", label: t.navAbout }];
    return [];
  });
  const inline = desktop && el.nav_links && links.length <= 5;
  const go = (id: string) => {
    setMenu(false);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const wordmark = (big = false) => b.logo
    ? <img className={`ed-logo ${big ? "ed-logo-big" : ""}`} src={b.logo} alt={company.name} />
    : <span className={big ? "ed-word ed-word-big" : "ed-word"} dir={D(company.name)}>{company.name}</span>;

  const heroBg = b.hero_image && b.hero_style !== "solid" ? b.hero_image : null;
  const pillars = el.trust ? t.trust.filter(Boolean) : [];

  return (
    <div className={`ed ${desktop ? "ed-web" : "ed-phone"}`}>
      <a className="ed-skip" href="#ed-main">{t.edSkip}</a>
      <header className={`ed-head ${scrolled || menu ? "ed-solid" : ""}`}>
        <a className="ed-brand" href="#top" onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: "smooth" }); }}>{wordmark()}</a>
        {inline && (
          <nav className="ed-nav" aria-label={company.name}>
            {links.map((l) => <a key={l.id} href={`#${l.id}`} onClick={(e) => { e.preventDefault(); go(l.id); }} dir={D(l.label)}>{l.label}</a>)}
            <a href={`/c/${ctx.slug}/me`}>{t.myTrips}</a>
          </nav>
        )}
        <div className="ed-head-end">
          {el.lang_switch && <button type="button" className="ed-lang" onClick={ctx.toggleLang} lang={lang === "ar" ? "en" : "ar"}>{t.switchTo}</button>}
          {desktop && <button type="button" className="ed-btn ed-btn-sm" onClick={plan}>{t.edCta}</button>}
          {!inline && (el.nav_links || !desktop) && (
            <button type="button" className="ed-menu-btn" aria-expanded={menu} aria-controls="ed-menu" onClick={() => setMenu(!menu)}>
              {menu ? t.edClose : t.edMenu} <span aria-hidden="true">{menu ? "–" : "+"}</span>
            </button>
          )}
        </div>
      </header>

      {menu && !inline && (
        <nav id="ed-menu" className="ed-menu" aria-label={company.name}>
          {links.map((l) => <a key={l.id} href={`#${l.id}`} onClick={(e) => { e.preventDefault(); go(l.id); }} dir={D(l.label)}>{l.label}</a>)}
          <a href={`/c/${ctx.slug}/me`}>{t.myTrips}</a>
          <button type="button" className="ed-btn" onClick={plan}>{t.edCta}</button>
        </nav>
      )}

      <section id="top" className={`ed-hero ${heroBg ? "ed-hero-photo" : ""}`} style={heroBg ? { backgroundImage: `url(${JSON.stringify(heroBg)})` } : undefined}>
        <div className="ed-hero-inner">
          {ctx.heroTitle
            ? <h1 className="ed-hero-title" dir={D(ctx.heroTitle)}><Emph text={ctx.heroTitle} /></h1>
            : <h1 className="ed-hero-mark">{wordmark(true)}</h1>}
          {tagline && <p className="ed-tagline" dir={D(tagline)}>{tagline}</p>}
          {ctx.heroText && <p className="ed-hero-text" dir={D(ctx.heroText)}>{ctx.heroText}</p>}
          <button type="button" className="ed-btn ed-btn-light" onClick={plan}>{t.edCta}</button>
        </div>
        {pillars.length > 0 && <ul className="ed-pillars">{pillars.map((x, i) => <li key={i} dir={D(x)}>{x}</li>)}</ul>}
      </section>

      <main id="ed-main">
        {ctx.blocks.map((blk) => <EdBlock key={blk} ctx={ctx} blk={blk} tripsBlock={tripsBlock} story={story} plan={plan} desktop={desktop} />)}

        <section className="ed-closing" aria-labelledby="ed-closing-title">
          <h2 id="ed-closing-title" className="ed-display" dir={D(t.edClosing)}><Emph text={t.edClosing} /></h2>
          <p className="ed-lead" dir={D(t.edClosingText)}>{t.edClosingText}</p>
          <button type="button" className="ed-btn ed-btn-light" onClick={plan}>{t.edCta}</button>
        </section>
      </main>

      <footer className="ed-foot">
        <div className="ed-foot-brand">{wordmark()}{tagline && <span className="ed-label" dir={D(tagline)}>{tagline}</span>}</div>
        <div className="ed-foot-links">
          {company.contact_email && <a href={`mailto:${company.contact_email}`}><Envelope /><bdi dir="ltr">{company.contact_email}</bdi></a>}
          {company.contact_phone && <a href={telLink(company.contact_phone)}><Phone /><bdi dir="ltr">{company.contact_phone}</bdi></a>}
          {ctx.whatsapp && <a href={ctx.whatsapp} target="_blank" rel="noreferrer"><WhatsappLogo />{t.whatsapp}</a>}
          <a href={`/c/${ctx.slug}/me`}>{t.myTrips}</a>
        </div>
        <div className="ed-foot-small">
          <span>© {new Date().getFullYear()} {company.name}. {t.edRights}</span>
          {el.footer_note && <span>{t.footer}</span>}
          <PoweredBy ctx={ctx} />
        </div>
      </footer>

      {pkg && (
        <Modal title={pkg.title} onClose={closePackage} wide>
          <WebPackage p={pkg} t={t} lang={lang} agent={agent} onClose={closePackage} onBook={() => ctx.book(pkg)} />
        </Modal>
      )}

      {chatOpen ? (
        <div className="sf-widget ed-chat" role="dialog" aria-label={t.chatWith(agent)}>
          <ChatHeader company={company} chat={chat} t={t} onClose={closeChat} onNew={ctx.askNew} compact />
          <ChatView chat={chat} t={t} lang={lang} packages={ctx.packages} onViewPackage={ctx.openPackage}
            inputRef={chatInput} live size="sm" onFocus={chat.ensure} />
        </div>
      ) : el.chat_launcher && (
        <button type="button" className={`ed-launcher ${scrolled ? "" : "ed-away"}`} onClick={ctx.openChat}>{t.chatWith(agent)}</button>
      )}
    </div>
  );
}

function EdBlock({ ctx, blk, tripsBlock, story, plan, desktop }: {
  ctx: StoreCtx; blk: Block; tripsBlock: Block | undefined; story: (k: StoryKey) => StorySection | undefined; plan: () => void; desktop: boolean;
}) {
  const { t, lang, agent } = ctx;
  if (blk === "featured" || blk === "offers") {
    if (blk !== tripsBlock) return null;
    const list = ctx.blocks.includes("offers") ? ctx.packages : ctx.featured;
    if (list.length === 0) return null;
    return (
      <section id="trips" className="ed-sec" aria-labelledby="ed-trips-title">
        <Head kicker={ctx.blocks.includes("offers") ? t.tripsOnSale : t.featuredTitle} id="ed-trips-title" />
        <Strip desktop={desktop} label={t.navTrips} t={t}>
          {list.map((p) => (
            <button key={p.id} type="button" className="ed-card" onClick={() => ctx.openPackage(p)}>
              <Photo src={p.image_url} alt="" initials={p.destination} />
              <span className="ed-card-title" dir={D(p.title)}>{p.title}</span>
              <span className="ed-card-meta" dir={D(p.destination)}>{p.destination}{p.country ? `, ${p.country}` : ""} · {t.days(p.duration_days)}</span>
              {ctx.cards.show_price && (
                <span className="ed-card-meta">{p.price_per_person == null ? t.onRequest
                  : <>{t.from} <Money value={p.price_per_person} currency={p.currency} lang={lang} /></>}</span>
              )}
            </button>
          ))}
        </Strip>
      </section>
    );
  }
  if (blk === "how") {
    const steps = t.how(agent, !!ctx.whatsapp);
    const bg = ctx.company.branding.how_bg_image;
    return (
      <section id="how" className="ed-sec ed-how" aria-labelledby="ed-how-title">
        {bg && <div className="ed-band" style={{ backgroundImage: `url(${JSON.stringify(bg)})` }} role="presentation" />}
        <div className="ed-wrap">
          <div className="ed-label">{t.howKicker}</div>
          <h2 id="ed-how-title" className="ed-display ed-center" dir={D(t.howTitle(agent))}>{t.howTitle(agent)} <em>{t.howAccent}</em> {t.howEnd}</h2>
          <ol className="ed-steps">
            {steps.map((s, i) => (
              <li key={i}><span className="ed-num">{num(i)}</span><h3 dir={D(s.title)}>{s.title}</h3><p dir={D(s.text)}>{s.text}</p></li>
            ))}
          </ol>
          <div className="ed-center"><button type="button" className="ed-btn" onClick={plan}>{t.edCta}</button></div>
        </div>
      </section>
    );
  }
  if (blk === "about") {
    const b = ctx.company.branding;
    if (!ctx.about && !ctx.showContact) return null;
    return (
      <section id="about" className="ed-sec ed-split" aria-labelledby="ed-about-title">
        {b.about_image && <Photo src={b.about_image} alt="" className="ed-split-photo" />}
        <div className="ed-split-text">
          <div className="ed-label">{t.navAbout}</div>
          <h2 id="ed-about-title" className="ed-display" dir={D(ctx.about?.title ?? t.contactTitle)}><Emph text={ctx.about?.title ?? t.contactTitle} /></h2>
          <p className="ed-body" dir={D(ctx.about?.text || t.contactText)}>{ctx.about?.text || t.contactText}</p>
        </div>
      </section>
    );
  }
  const k = blk as StoryKey;
  const s = story(k);
  const levels = k === "community" ? ctx.company.members ?? [] : [];
  if (!storyHasContent(s) && levels.length === 0) return null;
  const sec = s ?? { kicker_en: "", kicker_ar: "", title_en: "", title_ar: "", intro_en: "", intro_ar: "", image: null, items: [] };
  const kicker = storyNavLabel(ctx, k);
  const title = pick(lang, sec.title_en, sec.title_ar);
  const intro = pick(lang, sec.intro_en, sec.intro_ar);
  const items = sec.items;
  const titleId = `ed-${k}-title`;
  const it = (x: StoryItem) => ({
    title: pick(lang, x.title_en, x.title_ar), sub: pick(lang, x.subtitle_en, x.subtitle_ar),
    text: pick(lang, x.text_en, x.text_ar), tag: pick(lang, x.tag_en, x.tag_ar),
  });
  const head = <Head kicker={kicker} title={title} intro={intro} id={titleId} />;

  if (k === "mission" || k === "philosophy") {
    return (
      <section id={k} className={`ed-sec ed-statement ${k === "philosophy" ? "ed-ink" : ""}`} aria-labelledby={title ? titleId : undefined} aria-label={title ? undefined : kicker}>
        {sec.image && <div className="ed-band" style={{ backgroundImage: `url(${JSON.stringify(sec.image)})` }} role="presentation" />}
        <div className="ed-wrap ed-narrow">
          <div className="ed-label" dir={D(kicker)}>{kicker}</div>
          {title && <h2 id={titleId} className="ed-display" dir={D(title)}><Emph text={title} /></h2>}
          {intro && <p className={`ed-statement-text ${intro.length > 220 ? "ed-long" : ""}`} dir={D(intro)}>{intro}</p>}
          {items.length > 0 && <ul className="ed-ticks">{items.map((x, i) => <li key={i} dir={D(it(x).title + it(x).text)}><strong>{it(x).title}</strong>{it(x).text && ` ${it(x).text}`}</li>)}</ul>}
        </div>
      </section>
    );
  }
  if (k === "services") {
    return (
      <section id={k} className="ed-sec" aria-labelledby={title ? titleId : undefined} aria-label={title ? undefined : kicker}>
        {head}
        <ol className="ed-offers">
          {items.map((x, i) => {
            const v = it(x);
            return (
              <li key={i} className="ed-offer">
                <div className="ed-offer-head">
                  <span className="ed-num">{num(i)}</span>
                  <h3 className="ed-offer-title" dir={D(v.title)}><Emph text={v.title} /></h3>
                </div>
                <div className="ed-offer-body">
                  {v.sub && <p className="ed-label" dir={D(v.sub)}>{v.sub}</p>}
                  {v.text && <ul className="ed-offer-lines">{lines(v.text).map((l, j) => <li key={j} dir={D(l)}>{l}</li>)}</ul>}
                  {v.title && <button type="button" className="ed-link" onClick={() => ctx.ask(t.storyAskMsg(plain(v.title)))}>{t.storyAsk(agent)} <Arrow lang={lang} /></button>}
                </div>
                {x.image && <Photo src={x.image} alt="" className="ed-offer-photo" />}
              </li>
            );
          })}
        </ol>
        {sec.image && <div className="ed-band ed-band-after" style={{ backgroundImage: `url(${JSON.stringify(sec.image)})` }} role="presentation" />}
      </section>
    );
  }
  if (k === "experiences") {
    return (
      <section id={k} className="ed-sec" aria-labelledby={title ? titleId : undefined} aria-label={title ? undefined : kicker}>
        {head}
        <Strip desktop={desktop} label={kicker} t={t}>
          {items.map((x, i) => {
            const v = it(x);
            return (
              <button key={i} type="button" className="ed-card" onClick={() => v.title && ctx.ask(t.storyAskMsg(plain(v.title)))}>
                <Photo src={x.image} alt="" initials={plain(v.title)} />
                <span className="ed-card-title" dir={D(plain(v.title))}>{plain(v.title)}</span>
                {(v.tag || v.sub) && <span className="ed-card-meta" dir={D(v.tag + v.sub)}>{[v.tag, v.sub].filter(Boolean).join(" · ")}</span>}
              </button>
            );
          })}
        </Strip>
      </section>
    );
  }
  if (k === "leadership") {
    return (
      <section id={k} className="ed-sec" aria-labelledby={title ? titleId : undefined} aria-label={title ? undefined : kicker}>
        {head}
        {items.map((x, i) => {
          const v = it(x);
          return (
            <article key={i} className="ed-split ed-person">
              <Photo src={x.image} alt={v.title} className="ed-split-photo" initials={v.title} />
              <div className="ed-split-text">
                {v.title && <h3 className="ed-display ed-person-name" dir={D(v.title)}>{v.title}</h3>}
                {v.sub && <p className="ed-label" dir={D(v.sub)}>{v.sub}</p>}
                {v.text && <p className="ed-body" dir={D(v.text)}>{v.text}</p>}
              </div>
            </article>
          );
        })}
      </section>
    );
  }
  if (k === "faq") {
    return (
      <section id={k} className="ed-sec" aria-labelledby={title ? titleId : undefined} aria-label={title ? undefined : kicker}>
        {head}
        <div className="ed-faq">
          {items.map((x, i) => {
            const v = it(x);
            return <details key={i}><summary dir={D(v.title)}>{v.title}</summary><p dir={D(v.text)}>{v.text}</p></details>;
          })}
        </div>
      </section>
    );
  }
  // The Brand, Our promise, The Community: a title, the intro, numbered cards.
  return (
    <section id={k} className="ed-sec" aria-labelledby={title ? titleId : undefined} aria-label={title ? undefined : kicker}>
      {head}
      {sec.image && <Photo src={sec.image} alt="" className="ed-wide-photo" />}
      {k === "community" && levels.length > 0 && items.length === 0 ? (
        <div className="ed-grid">
          {levels.map((lv, i) => (
            <div key={lv.key} className="ed-pillar">
              <span className="ed-num">{num(i)}</span>
              <h3 dir="auto">{lang === "ar" ? lv.name_ar : lv.name_en}</h3>
              <ul className="ed-offer-lines">{(lang === "ar" ? lv.perks_ar : lv.perks_en).map((p, j) => <li key={j} dir={D(p)}>{p}</li>)}</ul>
            </div>
          ))}
        </div>
      ) : items.length > 0 && (
        <div className="ed-grid">
          {items.map((x, i) => {
            const v = it(x);
            return (
              <div key={i} className="ed-pillar">
                {x.image ? <Photo src={x.image} alt="" className="ed-pillar-photo" /> : <span className="ed-num">{num(i)}</span>}
                {v.tag && <span className="ed-label" dir={D(v.tag)}>{v.tag}</span>}
                {v.title && <h3 dir={D(v.title)}><Emph text={v.title} /></h3>}
                {v.sub && <p className="ed-label" dir={D(v.sub)}>{v.sub}</p>}
                {v.text && <p dir={D(v.text)}>{v.text}</p>}
              </div>
            );
          })}
        </div>
      )}
      {k === "community" && (
        <div className="ed-center"><button type="button" className="ed-btn" onClick={() => ctx.ask(t.joinMsg)}>{t.joinCommunity}</button></div>
      )}
    </section>
  );
}

function Head({ kicker, title, intro, id }: { kicker: string; title?: string; intro?: string; id: string }) {
  return (
    <div className="ed-sec-head">
      {title && <div className="ed-label" dir={D(kicker)}>{kicker}</div>}
      <h2 id={id} className="ed-display" dir={D(title || kicker)}><Emph text={title || kicker} /></h2>
      {intro && <p className="ed-lead" dir={D(intro)}>{intro}</p>}
    </div>
  );
}

/** A photo, or a quiet block with initials when there is none. */
function Photo({ src, alt, className = "", initials }: { src: string | null | undefined; alt: string; className?: string; initials?: string }) {
  if (src) return <img className={`ed-photo ${className}`} src={src} alt={alt} loading="lazy" />;
  const letters = (initials ?? "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w.charAt(0).toUpperCase()).join("");
  return <span className={`ed-photo ed-photo-empty ${className}`} role={alt ? "img" : undefined} aria-label={alt || undefined} aria-hidden={alt ? undefined : true}>{letters}</span>;
}

/** A row of portrait cards that scrolls sideways, with arrows on computers. */
function Strip({ children, desktop, label, t }: { children: ReactNode; desktop: boolean; label: string; t: StorefrontText }) {
  const ref = useRef<HTMLDivElement>(null);
  const move = (dir: number) => {
    const el = ref.current;
    if (!el) return;
    const rtl = getComputedStyle(el).direction === "rtl";
    el.scrollBy({ left: dir * (rtl ? -1 : 1) * el.clientWidth * 0.8, behavior: "smooth" });
  };
  return (
    <div className="ed-strip-wrap">
      <div ref={ref} className="ed-strip" role="list" aria-label={label}>
        {Array.isArray(children) ? children.map((c, i) => <div key={i} role="listitem" className="ed-strip-item">{c}</div>) : children}
      </div>
      {desktop && (
        <div className="ed-strip-arrows">
          <button type="button" className="ed-arrow" aria-label={t.edPrev} onClick={() => move(-1)}><ArrowLeft className="flip" /></button>
          <button type="button" className="ed-arrow" aria-label={t.edNext} onClick={() => move(1)}><ArrowRight className="flip" /></button>
        </div>
      )}
    </div>
  );
}

function Arrow({ lang }: { lang: string }) {
  return lang === "ar" ? <ArrowLeft /> : <ArrowRight />;
}
