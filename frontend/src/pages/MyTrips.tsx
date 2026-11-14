import { CSSProperties, FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ApiError, get, post } from "../api";
import { ChatCircleDots, Check, Crown, LockSimple, SignOut, Star, SuitcaseRolling, Translate, WhatsappLogo } from "../components/Icon";
import { moneyText } from "../components/Money";
import { pageVars } from "../components/storefront/style";
import { ErrorBox, Loading } from "../components/ui";
import { useI18n } from "../lang";
import { pinTheme } from "../themeMode";
import type { PublicCompany } from "../types";
import { dateTime, shortDate } from "../util";

interface Me { name: string | null; phone: string | null; company_name: string;
  member: { key: string; name_en: string; name_ar: string; perks_en: string[]; perks_ar: string[]; since: string | null } | null }
interface Trip {
  id: number; reference: string; title: string; departure_date: string | null; end_date: string | null; adults: number; children: number;
  total_price: number; currency: string; status: string; phase: "booking" | "upcoming" | "travelling" | "finished" | "cancelled";
  steps: { action: string; at: string }[]; rating: number | null; comment: string | null; can_rate: boolean;
}
interface Chat { id: number; channel: string; created_at: string; last_message_at: string; messages: { sender: string; content: string; created_at: string }[] }
interface Req { title: string; kind: string; status: string; created_at: string }

const PHASE: Record<Trip["phase"], string> = {
  booking: "Waiting for payment", upcoming: "Upcoming", travelling: "Travelling now", finished: "Finished", cancelled: "Cancelled",
};
const TRACK = ["Booked", "Paid", "Confirmed", "Travelling", "Back home"];

function trackIndex(t: Trip): number {
  if (t.phase === "finished") return 4;
  if (t.phase === "travelling") return 3;
  if (t.status === "confirmed") return 2;
  if (t.status === "paid") return 1;
  return 0;
}

const storageKey = (slug: string) => `gj_trips_${slug}`;
function readToken(slug: string): string | null {
  try { return localStorage.getItem(storageKey(slug)); } catch { return null; }
}
function saveToken(slug: string, token: string | null) {
  try { if (token) localStorage.setItem(storageKey(slug), token); else localStorage.removeItem(storageKey(slug)); } catch { /* storage blocked */ }
}

function SignIn({ slug, company, onToken }: { slug: string; company: PublicCompany; onToken: (t: string) => void }) {
  const { t } = useI18n();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wa = company.whatsapp_number ? `https://wa.me/${company.whatsapp_number.replace(/\D/g, "")}?text=${encodeURIComponent("My trips")}` : null;
  const send = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await post(`/api/public/companies/${slug}/me/code`, { phone }, { customerToken: null }); setSent(true); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  const verify = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { onToken((await post<{ token: string }>(`/api/public/companies/${slug}/me/verify`, { phone, code }, { customerToken: null })).token); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="mt-card mt-signin">
      <LockSimple className="mt-lock" />
      <h1>{t("Your private trips page")}</h1>
      <p className="mt-muted">{t("Your bookings, the progress of each trip and your chats with us. Only you can open it, with your WhatsApp number.")}</p>
      {!sent ? (
        <form onSubmit={send} className="mt-form">
          <label htmlFor="mt-phone">{t("Your WhatsApp number")}</label>
          <input id="mt-phone" value={phone} onChange={(e) => setPhone(e.target.value)} dir="ltr" inputMode="tel" placeholder="+968 9123 4567" required />
          <button className="sf-cta" disabled={busy}>{busy ? t("Sending…") : t("Send me a code on WhatsApp")}</button>
        </form>
      ) : (
        <form onSubmit={verify} className="mt-form">
          <label htmlFor="mt-code">{t("The 6-digit code we sent to your WhatsApp")}</label>
          <input id="mt-code" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} dir="ltr" inputMode="numeric"
            autoComplete="one-time-code" placeholder="123456" required minLength={6} />
          <button className="sf-cta" disabled={busy || code.length !== 6}>{busy ? t("Checking…") : t("Open my trips")}</button>
          <button type="button" className="link-btn" onClick={() => { setSent(false); setCode(""); }}>{t("Use another number")}</button>
        </form>
      )}
      <ErrorBox error={error} />
      <p className="mt-muted mt-small">{t("No code? WhatsApp lets us message you only within 24 hours of your last message to us. Write to us first, or simply ask for \"my trips\" in our WhatsApp chat and we'll send you a private link.")}</p>
      {wa && <a className="btn btn-wa sf-pill" href={wa} target="_blank" rel="noreferrer"><WhatsappLogo weight="fill" />{t("Ask for my link on WhatsApp")}</a>}
    </div>
  );
}

function Stars({ value, onPick }: { value: number; onPick?: (n: number) => void }) {
  const { t } = useI18n();
  return (
    <span className="mt-stars" role={onPick ? "radiogroup" : undefined} aria-label={t("Rating")}>
      {[1, 2, 3, 4, 5].map((n) => onPick ? (
        <button key={n} type="button" role="radio" aria-checked={value === n} aria-label={`${n}`} className={n <= value ? "on" : ""} onClick={() => onPick(n)}><Star weight="fill" /></button>
      ) : <Star key={n} weight="fill" className={n <= value ? "on" : ""} aria-hidden="true" />)}
    </span>
  );
}

function TripCard({ trip, onRate }: { trip: Trip; onRate: (id: number, rating: number, comment: string) => Promise<void> }) {
  const { t, lang } = useI18n();
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const idx = trackIndex(trip);
  const travellers = t("{a} adults", { a: trip.adults }) + (trip.children ? ` · ${t("{c} children", { c: trip.children })}` : "");
  return (
    <article className={`mt-card mt-trip mt-${trip.phase}`}>
      <div className="mt-trip-head">
        <div><div className="mt-ref">{trip.reference}</div><h3 dir="auto">{trip.title}</h3></div>
        <span className={`mt-phase mt-phase-${trip.phase}`}>{t(PHASE[trip.phase])}</span>
      </div>
      <div className="mt-facts">
        <span>{shortDate(trip.departure_date)}{trip.end_date && trip.end_date !== trip.departure_date ? ` – ${shortDate(trip.end_date)}` : ""}</span>
        <span>{travellers}</span>
        <strong>{moneyText(trip.total_price, trip.currency, lang)}</strong>
      </div>
      {trip.phase !== "cancelled" && (
        <ol className="mt-track" aria-label={t("Trip progress")}>
          {TRACK.map((s, i) => <li key={s} className={i <= idx ? "done" : ""} aria-current={i === idx ? "step" : undefined}><span>{i < idx || (trip.phase === "finished" && i === idx) ? <Check /> : i + 1}</span>{t(s)}</li>)}
        </ol>
      )}
      {trip.rating !== null && <div className="mt-rated"><Stars value={trip.rating} />{trip.comment && <span dir="auto">“{trip.comment}”</span>}</div>}
      {trip.can_rate && (
        <form className="mt-rate" onSubmit={(e) => { e.preventDefault(); setError(null); onRate(trip.id, rating, comment).catch((err) => setError((err as Error).message)); }}>
          <div className="mt-rate-q">{t("How was your trip?")}</div>
          <Stars value={rating} onPick={setRating} />
          <textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} maxLength={2000} dir="auto" placeholder={t("A few words about your trip (optional)")} />
          <button className="sf-cta sf-sm" disabled={!rating}>{t("Send my rating")}</button>
          <ErrorBox error={error} />
        </form>
      )}
    </article>
  );
}

export default function MyTrips() {
  const { slug = "" } = useParams();
  const { hash } = useLocation();
  const { t, lang, setLang } = useI18n();
  const [company, setCompany] = useState<PublicCompany | null>(null);
  const [token, setToken] = useState<string | null>(() => readToken(slug));
  const [me, setMe] = useState<Me | null>(null);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [chats, setChats] = useState<Chat[]>([]);
  const [reqs, setReqs] = useState<Req[]>([]);
  const [tab, setTab] = useState<"trips" | "chats" | "requests">("trips");
  const [openChat, setOpenChat] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [linkError, setLinkError] = useState<string | null>(null);

  useEffect(() => {
    document.body.classList.add("sf-body");
    const unpin = pinTheme("dark");
    get<PublicCompany>(`/api/public/companies/${slug}`).then(setCompany).catch((e) => setError((e as Error).message));
    return () => { document.body.classList.remove("sf-body"); unpin(); };
  }, [slug]);

  // A private link from the WhatsApp chat: the key is after "#", exchanged once, then removed from the address.
  useEffect(() => {
    const key = new URLSearchParams(hash.slice(1)).get("k");
    if (!key) return;
    window.history.replaceState(null, "", window.location.pathname);
    post<{ token: string }>(`/api/public/companies/${slug}/me/link`, { key }, { customerToken: null })
      .then((r) => { saveToken(slug, r.token); setToken(r.token); setLinkError(null); }).catch((e) => setLinkError((e as Error).message));
  }, [slug, hash]);

  const signOut = useCallback(() => { saveToken(slug, null); setToken(null); setMe(null); }, [slug]);
  const load = useCallback(() => {
    if (!token) return;
    const o = { customerToken: token };
    const base = `/api/public/companies/${slug}/me`;
    Promise.all([get<Me>(base, o), get<Trip[]>(`${base}/trips`, o), get<Chat[]>(`${base}/chats`, o), get<Req[]>(`${base}/requests`, o)])
      .then(([m, tr, ch, rq]) => { setMe(m); setTrips(tr); setChats(ch); setReqs(rq); setError(null); })
      .catch((e) => { if (e instanceof ApiError && e.status === 401) signOut(); else setError((e as Error).message); });
  }, [slug, token, signOut]);
  useEffect(load, [load]);

  const rate = async (id: number, rating: number, comment: string) => {
    setTrips(await post<Trip[]>(`/api/public/companies/${slug}/me/trips/${id}/feedback`, { rating, comment: comment || null }, { customerToken: token }));
  };
  const everywhere = async () => {
    try { await post(`/api/public/companies/${slug}/me/logout-everywhere`, {}, { customerToken: token }); } finally { signOut(); }
  };

  const style = (company ? pageVars(company.branding) : {}) as CSSProperties;
  const upcoming = trips.filter((x) => ["booking", "upcoming", "travelling"].includes(x.phase));
  const past = trips.filter((x) => ["finished", "cancelled"].includes(x.phase));
  const member = me?.member;

  return (
    <div className="sf mt" style={style} dir={lang === "ar" ? "rtl" : "ltr"} lang={lang}>
      <div className="sf-orbs" aria-hidden="true" />
      <header className="mt-top">
        <Link to={`/c/${slug}`} className="mt-brand" dir="auto">{company?.name ?? ""}</Link>
        <span className="mt-grow" />
        <button type="button" className="sf-lang" onClick={() => setLang(lang === "ar" ? "en" : "ar")}><Translate />{lang === "ar" ? "English" : "العربية"}</button>
        {me && <button type="button" className="sf-lang" onClick={signOut}><SignOut className="flip" />{t("Sign out")}</button>}
      </header>
      <main className="mt-main">
        {linkError && <ErrorBox error={linkError} />}
        {!company ? (error ? <ErrorBox error={error} /> : <Loading height={240} />)
          : !token ? <SignIn slug={slug} company={company} onToken={(tk) => { saveToken(slug, tk); setToken(tk); }} />
          : !me ? (error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={240} />) : (<>
            <section className="mt-hello">
              <h1 dir="auto">{me.name ? t("Hello, {name}", { name: me.name }) : t("Your trips")}</h1>
              {member && (
                <div className="mt-card mt-member">
                  <div className="mt-member-name"><Crown weight="fill" />{lang === "ar" ? member.name_ar : member.name_en}</div>
                  <ul>{(lang === "ar" ? member.perks_ar : member.perks_en).map((p, i) => <li key={i}>{p}</li>)}</ul>
                </div>
              )}
            </section>
            <div className="mt-tabs" role="tablist">
              <button type="button" role="tab" aria-selected={tab === "trips"} className={tab === "trips" ? "on" : ""} onClick={() => setTab("trips")}><SuitcaseRolling />{t("Trips")} <span>{trips.length}</span></button>
              <button type="button" role="tab" aria-selected={tab === "chats"} className={tab === "chats" ? "on" : ""} onClick={() => setTab("chats")}><ChatCircleDots />{t("Chats")} <span>{chats.length}</span></button>
              {reqs.length > 0 && <button type="button" role="tab" aria-selected={tab === "requests"} className={tab === "requests" ? "on" : ""} onClick={() => setTab("requests")}><Crown />{t("My requests")} <span>{reqs.length}</span></button>}
            </div>
            {tab === "trips" && (trips.length === 0 ? <p className="mt-muted">{t("No bookings yet. Ask us in the chat and we'll plan your next trip.")}</p> : (<>
              {upcoming.length > 0 && <h2 className="mt-h2">{t("Current and upcoming")}</h2>}
              {upcoming.map((x) => <TripCard key={x.id} trip={x} onRate={rate} />)}
              {past.length > 0 && <h2 className="mt-h2">{t("Past trips")}</h2>}
              {past.map((x) => <TripCard key={x.id} trip={x} onRate={rate} />)}
            </>))}
            {tab === "chats" && (chats.length === 0 ? <p className="mt-muted">{t("No chats yet.")}</p> : chats.map((c) => (
              <article key={c.id} className="mt-card mt-chat">
                <button type="button" className="mt-chat-head" aria-expanded={openChat === c.id} onClick={() => setOpenChat(openChat === c.id ? null : c.id)}>
                  {c.channel === "whatsapp" ? <WhatsappLogo /> : <ChatCircleDots />}
                  <span>{dateTime(c.created_at)}</span><span className="mt-grow" /><span className="mt-muted">{t("{n} messages", { n: c.messages.length })}</span>
                </button>
                {openChat === c.id && (
                  <div className="mt-msgs">
                    {c.messages.map((m, i) => (
                      <div key={i} className={`mt-msg ${m.sender === "customer" ? "me" : ""}`}>
                        <div dir="auto">{m.content}</div><time>{dateTime(m.created_at)}</time>
                      </div>
                    ))}
                  </div>
                )}
              </article>
            )))}
            {tab === "requests" && reqs.map((r, i) => (
              <article key={i} className="mt-card mt-req"><strong dir="auto">{r.title}</strong><span className="mt-muted">{dateTime(r.created_at)}</span><span className={`mt-phase mt-req-${r.status}`}>{t({ open: "Received", in_progress: "In progress", done: "Done", declined: "Not possible" }[r.status] ?? r.status)}</span></article>
            ))}
            <p className="mt-muted mt-small mt-foot">
              <LockSimple /> {t("This page is private to you.")} <button type="button" className="link-btn" onClick={everywhere}>{t("Sign out on all devices")}</button>
            </p>
          </>)}
      </main>
    </div>
  );
}
