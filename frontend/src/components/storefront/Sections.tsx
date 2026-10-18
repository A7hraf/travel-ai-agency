import { Binoculars, ChatCircleDots, Envelope, Headset, Phone, Receipt, SunHorizon, WhatsappLogo } from "../Icon";
import { GhanjahMark } from "../Brand";
import { telLink } from "./shared";
import type { StoreCtx } from "./context";

/** Agency logo, or the design's glowing sun mark. */
export function AgencyMark({ ctx, size = 38 }: { ctx: StoreCtx; size?: number }) {
  const logo = ctx.company.branding.logo;
  if (logo) return <img className="sf-logo-img" src={logo} alt="" style={{ height: size }} />;
  return <span className="sf-sunmark" style={{ width: size, height: size, fontSize: size * 0.53 }} aria-hidden="true"><SunHorizon weight="fill" /></span>;
}

/** All / Honeymoon / Family / … (chips that match no package are hidden). */
export function CategoryChips({ ctx, className = "" }: { ctx: StoreCtx; className?: string }) {
  if (ctx.cats.length < 2) return null;
  return (
    <div className={`sf-chips ${className}`} role="group" aria-label={ctx.t.categoriesLabel}>
      {ctx.cats.map((i) => (
        <button key={i} type="button" className={`sf-chip ${ctx.cat === i ? "sf-active" : ""}`} aria-pressed={ctx.cat === i}
          onClick={() => ctx.setCat(i)}>{ctx.t.categories[i]}</button>
      ))}
    </div>
  );
}

/** No package matches, or the agency has no packages yet. */
export function TripsEmpty({ ctx }: { ctx: StoreCtx }) {
  const { t, agent } = ctx;
  if (ctx.packages.length === 0) {
    return (
      <div className="sf-empty">
        <Binoculars className="sf-empty-icon" />
        <div className="sf-empty-title">{t.comingSoon}</div>
        <button type="button" className="sf-cta" onClick={ctx.openChat}>{t.askNow(agent)}</button>
      </div>
    );
  }
  return (
    <div className="sf-empty">
      <Binoculars className="sf-empty-icon" />
      <div className="sf-empty-title">{t.noMatch}</div>
      <div className="sf-empty-actions">
        <button type="button" className="sf-cta" onClick={ctx.openChat}>{t.askCustom(agent)}</button>
        <button type="button" className="link-btn" onClick={ctx.clearFilters}>{t.clear}</button>
      </div>
    </div>
  );
}

/** "How booking works": three cards with outlined numerals. */
export function HowSteps({ ctx }: { ctx: StoreCtx }) {
  const { t, agent } = ctx;
  const icons = [ChatCircleDots, Receipt, Headset];
  return (
    <section id="how" className="sf-how" aria-labelledby="sf-how-title">
      <div className="sf-kicker-cyan">{t.howKicker}</div>
      <h2 id="sf-how-title" className="sf-how-title">{t.howTitle(agent)} <em className="sf-accent">{t.howAccent}</em> {t.howEnd}</h2>
      <div className="sf-how-grid">
        {t.how(agent, !!ctx.whatsapp).map((step, i) => {
          const Icon = icons[i];
          return (
            <div key={i} className="sf-how-card">
              <div className="sf-how-num" aria-hidden="true">{i + 1}</div>
              <div className="sf-how-head"><Icon className="sf-how-icon" /><h3>{step.title}</h3></div>
              <p>{step.text}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function ContactButtons({ ctx }: { ctx: StoreCtx }) {
  const { company, t } = ctx;
  return (
    <div className="sf-contact-btns">
      {ctx.whatsapp && <a className="btn btn-wa sf-pill" href={ctx.whatsapp} target="_blank" rel="noreferrer"><WhatsappLogo weight="fill" />{t.whatsapp}</a>}
      {company.contact_phone && <a className="btn sf-pill" href={telLink(company.contact_phone)} aria-label={`${t.phone} ${company.contact_phone}`}><Phone /><bdi dir="ltr">{company.contact_phone}</bdi></a>}
      {company.contact_email && <a className="btn sf-pill" href={`mailto:${company.contact_email}`} aria-label={`${t.email} ${company.contact_email}`}><Envelope /><bdi dir="ltr">{company.contact_email}</bdi></a>}
      {!ctx.whatsapp && !company.contact_phone && !company.contact_email && (
        <button type="button" className="btn btn-primary sf-pill" onClick={ctx.openChat}><ChatCircleDots />{t.chatWith(ctx.agent)}</button>
      )}
    </div>
  );
}

/** About pull-quote and text, with the contact buttons (or the contact block alone). */
export function AboutBlock({ ctx }: { ctx: StoreCtx }) {
  const { t, about, showContact } = ctx;
  if (!about && !showContact) return null;
  return (
    <section id="about" className="sf-about" aria-labelledby="sf-about-title">
      <div className="sf-about-side">
        <div id="sf-about-title" className="sf-kicker-cyan" dir="auto">{about ? about.title : t.contactTitle}</div>
        <blockquote className="sf-quote-big">{about ? t.aboutQuote : t.contactText}</blockquote>
      </div>
      <div className="sf-about-main">
        {about && <p className="sf-about-text" dir="auto">{about.text}</p>}
        {showContact && <ContactButtons ctx={ctx} />}
      </div>
    </section>
  );
}

export function PoweredBy({ ctx }: { ctx: StoreCtx }) {
  return (
    <a className="sf-powered" href="/" aria-label={ctx.t.poweredBy}>
      <GhanjahMark dark size={22} /><span>{ctx.t.poweredBy}</span>
    </a>
  );
}
