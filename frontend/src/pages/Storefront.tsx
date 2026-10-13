import { CSSProperties, FormEvent, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, get, post } from "../api";
import { Lang, Money } from "../components/Money";
import { ChatText, Modal } from "../components/ui";
import { STOREFRONT_TEXT, StorefrontText, useLang } from "../i18n";
import { storefrontVars } from "../theme";
import type { PublicCompany, PublicMessage, TravelPackage } from "../types";
import { gradientFor, shortDate } from "../util";

function cover(p: TravelPackage) {
  return p.image_url ? `center / cover no-repeat url(${JSON.stringify(p.image_url)})` : gradientFor(p.destination);
}

function PackageCard({ p, lang, t, onOpen, onBook }: {
  p: TravelPackage; lang: Lang; t: StorefrontText; onOpen: () => void; onBook: () => void;
}) {
  return (
    <article className="pkg-card sf-card" onClick={onOpen} tabIndex={0} aria-label={t.openPackage(p.title)}
      onKeyDown={(e) => {
        if ((e.key === "Enter" || e.key === " ") && e.target === e.currentTarget) {
          e.preventDefault();
          onOpen();
        }
      }}>
      <div className="pkg-cover" style={{ background: cover(p) }}>
        <span>{p.destination}, {p.country}</span>
        {p.is_featured && <span className="pkg-flag">{t.featured}</span>}
      </div>
      <div className="pkg-body">
        <h3>{p.title}</h3>
        <div className="muted small">{t.days(p.duration_days)}{p.hotel_stars ? ` · ${"★".repeat(p.hotel_stars)} ${t.starHotel}` : ""}</div>
        <div className="tag-row">{p.tags.slice(0, 4).map((tag) => <span key={tag} className="tag">{tag}</span>)}</div>
        <div className="row-between">
          <div className="pkg-price"><Money value={p.price_per_person} currency={p.currency} lang={lang} /><span className="muted small"> {t.perPerson}</span></div>
          <button className="btn btn-sm btn-primary" onClick={(e) => { e.stopPropagation(); onBook(); }}>{t.book}</button>
        </div>
      </div>
    </article>
  );
}

export default function Storefront() {
  const { slug = "" } = useParams();
  const [lang, setLang] = useLang();
  const t = STOREFRONT_TEXT[lang];
  const [company, setCompany] = useState<PublicCompany | null>(null);
  const [packages, setPackages] = useState<TravelPackage[]>([]);
  const [notFound, setNotFound] = useState(false);
  const [query, setQuery] = useState("");
  const [budget, setBudget] = useState("");
  const [selected, setSelected] = useState<TravelPackage | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [prefill, setPrefill] = useState<string | null>(null);

  useEffect(() => {
    get<PublicCompany>(`/api/public/companies/${slug}`).then((c) => {
      setCompany(c);
      document.title = c.name;
    }).catch(() => setNotFound(true));
    get<TravelPackage[]>(`/api/public/companies/${slug}/packages`).then(setPackages).catch(() => {});
  }, [slug]);

  if (notFound) return <div className="sf-missing">{t.notFound}</div>;
  if (!company) return <div className="loading-screen">{t.loading}</div>;

  const b = company.branding;
  const shown = packages.filter((p) => {
    const text = `${p.title} ${p.destination} ${p.country} ${p.tags.join(" ")} ${p.description}`.toLowerCase();
    return (!query || text.includes(query.toLowerCase())) && (!budget || p.price_per_person <= Number(budget));
  });
  // While the visitor searches, only the matching offers are shown (no featured block above them).
  const filtering = !!(query.trim() || budget);
  const featured = filtering ? [] : packages.filter((p) => p.is_featured);

  const askAbout = (p: TravelPackage) => {
    setSelected(null);
    setPrefill(t.interested(p.title, p.duration_days));
    setChatOpen(true);
  };
  const waDigits = company.whatsapp_number?.replace(/\D/g, "");
  const agent = company.ai_agent_name;
  const heroTitle = (lang === "ar" ? b.hero_title_ar : b.hero_title_en) || t.heroTitle;
  const heroText = (lang === "ar" ? b.hero_text_ar : b.hero_text_en) || t.heroText(agent);
  const aboutTitle = (lang === "ar" ? b.about_title_ar : b.about_title_en) || t.aboutTitle;
  const aboutText = lang === "ar" ? b.about_ar || b.about_en : b.about_en || b.about_ar;
  const heroStyle: CSSProperties | undefined = b.hero_style === "image" && b.hero_image
    ? { backgroundImage: `linear-gradient(rgb(0 0 0 / 35%), rgb(0 0 0 / 60%)), url(${JSON.stringify(b.hero_image)})` }
    : undefined;
  const gridClass = `pkg-grid ${b.layout === "list" ? "list" : ""} ${b.card_style === "square" ? "square" : ""}`;
  const card = (p: TravelPackage) => (
    <PackageCard key={p.id} p={p} lang={lang} t={t} onOpen={() => setSelected(p)} onBook={() => askAbout(p)} />
  );

  const sections: Record<string, ReactNode> = {
    featured: featured.length > 0 && (
      <section key="featured" className="sf-section">
        <h2>{t.featuredTitle}</h2>
        <div className={gridClass}>{featured.slice(0, 3).map(card)}</div>
      </section>
    ),
    offers: (
      <section key="offers" className="sf-section">
        <div className="sf-offers-head">
          <h2>{t.offers}</h2>
          {company.currency === "OMR" && <span className="muted small">{t.pricesNote}</span>}
        </div>
        {packages.length === 0 ? (
          <p className="muted">{t.comingSoon(agent)} <button className="link-btn" onClick={() => setChatOpen(true)}>{t.askNow}</button></p>
        ) : shown.length === 0 ? (
          <p className="muted">{t.noMatch} <button className="link-btn" onClick={() => setChatOpen(true)}>{t.askFor(agent)}</button> {t.customTrip}</p>
        ) : (
          <div className={gridClass}>{shown.map(card)}</div>
        )}
      </section>
    ),
    about: aboutText && (
      <section key="about" className="sf-section sf-about">
        <h2>{aboutTitle}</h2>
        <p dir="auto">{aboutText}</p>
      </section>
    ),
    contact: (
      <section key="contact" className="sf-section sf-contact-card">
        <div>
          <h2>{t.contactTitle}</h2>
          <p className="muted">{t.contactText}</p>
        </div>
        <div className="sf-contact-actions">
          {company.contact_phone && <a className="btn" href={`tel:${company.contact_phone.replace(/[^\d+]/g, "")}`} dir="ltr">☎ {company.contact_phone}</a>}
          {company.contact_email && <a className="btn" href={`mailto:${company.contact_email}`} dir="ltr">✉ {company.contact_email}</a>}
          {waDigits && <a className="btn btn-wa" href={`https://wa.me/${waDigits}`} target="_blank" rel="noreferrer">{t.whatsapp}</a>}
          <button className="btn btn-primary" onClick={() => setChatOpen(true)}>💬 {t.chatWith(agent)}</button>
        </div>
      </section>
    ),
  };

  return (
    <div className={`sf ${b.card_style === "square" ? "sf-square" : ""}`} dir={lang === "ar" ? "rtl" : "ltr"} lang={lang}
      style={storefrontVars(b.primary_color, b.accent_color) as CSSProperties}>
      <header className={`sf-hero hero-${b.hero_style}`} style={heroStyle}>
        <div className="sf-nav">
          <div className="sf-logo">
            {b.logo ? <img src={b.logo} alt="" /> : <span>✈</span>}
            <span>{company.name}</span>
          </div>
          <div className="sf-contact">
            {company.contact_phone && <span dir="ltr">☎ {company.contact_phone}</span>}
            {waDigits && <a className="btn btn-wa btn-sm" href={`https://wa.me/${waDigits}`} target="_blank" rel="noreferrer">{t.whatsapp}</a>}
            <button className="btn btn-sm lang-switch" onClick={() => setLang(lang === "ar" ? "en" : "ar")}>{t.switchTo}</button>
          </div>
        </div>
        <div className="sf-hero-text">
          <h1 dir="auto">{heroTitle}</h1>
          <p dir="auto">{heroText}</p>
          {b.sections.includes("search") ? (
            <div className="sf-search">
              <input type="search" placeholder={t.searchPlaceholder} aria-label={t.searchLabel} value={query} onChange={(e) => setQuery(e.target.value)} />
              <input type="number" min={0} inputMode="decimal" placeholder={t.budgetPlaceholder} aria-label={t.budgetLabel} value={budget} onChange={(e) => setBudget(e.target.value)} />
              <button className="btn btn-primary" onClick={() => setChatOpen(true)}>{t.chatWith(agent)}</button>
            </div>
          ) : (
            <button className="btn btn-primary sf-hero-cta" onClick={() => setChatOpen(true)}>{t.chatWith(agent)}</button>
          )}
        </div>
      </header>

      <main className="sf-main">
        {b.sections.filter((s) => s !== "search").map((s) => sections[s])}
      </main>

      <footer className="sf-footer">
        {company.name}{company.contact_email && <> · <bdi dir="ltr">{company.contact_email}</bdi></>} · {t.footer}
      </footer>

      {selected && (
        <Modal title={selected.title} onClose={() => setSelected(null)} wide>
          <div dir={lang === "ar" ? "rtl" : "ltr"}>
            <div className="pkg-cover big" style={{ background: cover(selected) }}>
              <span>{selected.destination}, {selected.country} · {t.days(selected.duration_days)}</span>
            </div>
            <p>{selected.description}</p>
            <div className="grid-2">
              <div>
                <h4>{t.included}</h4>
                <ul className="ticks">{selected.includes.map((i) => <li key={i}>{i}</li>)}</ul>
              </div>
              <div>
                <h4>{t.notIncluded}</h4>
                <ul className="crosses">{selected.excludes.map((i) => <li key={i}>{i}</li>)}</ul>
              </div>
            </div>
            <dl className="details">
              <dt>{t.hotel}</dt><dd>{selected.hotel_name ?? "—"} {selected.hotel_stars ? "★".repeat(selected.hotel_stars) : ""}</dd>
              <dt>{t.departures}</dt><dd>{selected.departure_dates.length ? selected.departure_dates.map(shortDate).join(" · ") : t.flexible}</dd>
              <dt>{t.price}</dt><dd><strong><Money value={selected.price_per_person} currency={selected.currency} lang={lang} /></strong> {t.perAdult}
                {selected.child_price != null && <> · <Money value={selected.child_price} currency={selected.currency} lang={lang} /> {t.perChild}</>}</dd>
              {selected.seats_available != null && <><dt>{t.seatsLeft}</dt><dd>{selected.seats_available}</dd></>}
            </dl>
            <div className="modal-actions"><span className="spacer" />
              <button className="btn btn-primary" onClick={() => askAbout(selected)}>{t.bookWith(agent)}</button>
            </div>
          </div>
        </Modal>
      )}

      {chatOpen ? (
        <ChatWidget slug={slug} company={company} lang={lang} t={t} prefill={prefill}
          onPrefillUsed={() => setPrefill(null)} onClose={() => setChatOpen(false)} />
      ) : (
        <button className="chat-fab" onClick={() => setChatOpen(true)}><span aria-hidden="true">💬</span> <span className="chat-fab-text">{t.chatWith(agent)}</span></button>
      )}
    </div>
  );
}

function ChatWidget({ slug, company, lang, t, prefill, onPrefillUsed, onClose }: {
  slug: string; company: PublicCompany; lang: Lang; t: StorefrontText; prefill: string | null;
  onPrefillUsed: () => void; onClose: () => void;
}) {
  const storageKey = `travel_chat_${slug}`;
  const [token, setToken] = useState<string | null>(null);
  const [messages, setMessages] = useState<PublicMessage[]>([]);
  const [status, setStatus] = useState("ai");
  const [text, setText] = useState("");
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const started = useRef(false);
  const base = `/api/public/companies/${slug}/chats`;

  const merge = useCallback((incoming: PublicMessage[]) => {
    setMessages((prev) => {
      const known = new Set(prev.filter((m) => m.id > 0).map((m) => m.id));
      const kept = prev.filter((m) => m.id > 0);
      return [...kept, ...incoming.filter((m) => !known.has(m.id))].sort((a, b) => a.id - b.id);
    });
  }, []);

  const startNew = useCallback(async () => {
    const res = await post<{ token: string; status: string; messages: PublicMessage[] }>(base, { lang });
    try { localStorage.setItem(storageKey, res.token); } catch { /* ignore */ }
    setToken(res.token);
    setStatus(res.status);
    setMessages(res.messages);
    return res.token;
  }, [base, storageKey, lang]);

  // Resume the previous chat on this device, or start a new one.
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    let saved: string | null = null;
    try { saved = localStorage.getItem(storageKey); } catch { /* ignore */ }
    if (!saved) { startNew().catch((e) => setError(e.message)); return; }
    get<{ status: string; messages: PublicMessage[] }>(`${base}/${saved}/messages?after_id=0`)
      .then((r) => { setToken(saved); setStatus(r.status); setMessages(r.messages); })
      .catch(() => startNew().catch((e) => setError(e.message)));
  }, [base, storageKey, startNew]);

  // Pick up replies written by employees.
  useEffect(() => {
    if (!token) return;
    const id = window.setInterval(() => {
      if (waiting || document.visibilityState !== "visible") return;
      const last = messages.filter((m) => m.id > 0).slice(-1)[0]?.id ?? 0;
      get<{ status: string; messages: PublicMessage[] }>(`${base}/${token}/messages?after_id=${last}`)
        .then((r) => { setStatus(r.status); if (r.messages.length) merge(r.messages); })
        .catch(() => {});
    }, 5000);
    return () => window.clearInterval(id);
  }, [token, messages, waiting, base, merge]);

  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [messages, waiting]);
  // Ready to type as soon as the chat is open.
  useEffect(() => { if (token) input.current?.focus(); }, [token]);

  const send = useCallback(async (content: string) => {
    if (!content.trim() || !token) return;
    setError(null);
    setWaiting(true);
    setMessages((prev) => [...prev, { id: -Date.now(), sender: "customer", content, created_at: new Date().toISOString() }]);
    try {
      const r = await post<{ status: string; messages: PublicMessage[] }>(`${base}/${token}/messages`, { content });
      setStatus(r.status);
      merge(r.messages);
    } catch (e) {
      setMessages((prev) => prev.filter((m) => m.id > 0));
      setError(e instanceof ApiError && e.status === 429 ? t.tooFast : t.notSent);
      setText(content);
    } finally {
      setWaiting(false);
    }
  }, [token, base, merge, t]);

  useEffect(() => {
    if (prefill && token && !waiting) {
      onPrefillUsed();
      send(prefill);
    }
  }, [prefill, token, waiting, send, onPrefillUsed]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const content = text.trim();
    setText("");
    send(content);
  };

  const restart = () => {
    if (messages.some((m) => m.sender === "customer") && !window.confirm(t.confirmNewChat)) return;
    try { localStorage.removeItem(storageKey); } catch { /* ignore */ }
    setMessages([]);
    startNew().catch((e) => setError(e.message));
  };

  return (
    <div className="chat-widget" dir={lang === "ar" ? "rtl" : "ltr"}>
      <div className="cw-head">
        <div className="cw-avatar">{company.ai_agent_name.charAt(0)}</div>
        <div>
          <div className="cw-name">{company.ai_agent_name} · {company.name}</div>
          <div className="cw-sub">{status === "human" ? t.humanSub : t.aiSub}</div>
        </div>
        <button className="icon-btn light" title={t.newChat} aria-label={t.newChat} onClick={restart}>↻</button>
        <button className="icon-btn light" onClick={onClose} aria-label={t.close}>×</button>
      </div>
      <div className="cw-body" aria-live="polite" aria-relevant="additions">
        {messages.map((m) => (
          <div key={m.id} className={`cw-msg ${m.sender === "customer" ? "me" : "them"}`}>
            {m.sender === "agent" && <div className="cw-who">{t.consultant}</div>}
            <div className="cw-bubble" dir="auto"><ChatText text={m.content} /></div>
          </div>
        ))}
        {waiting && status !== "human" && <div className="cw-msg them"><div className="cw-bubble typing"><span /><span /><span /></div></div>}
        <div ref={bottom} />
      </div>
      {error && <div className="cw-error">{error}</div>}
      <form className="cw-input" onSubmit={submit}>
        <input ref={input} value={text} onChange={(e) => setText(e.target.value)} placeholder={t.typeHere} aria-label={t.messageLabel}
          disabled={!token} maxLength={2000} dir="auto" autoFocus />
        <button className="btn btn-primary" disabled={!text.trim() || waiting || !token}>{t.send}</button>
      </form>
    </div>
  );
}
