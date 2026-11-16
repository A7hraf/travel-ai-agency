import { ChangeEvent, CSSProperties, FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ApiError, download, get, post, readFileBase64 } from "../api";
import { PART_LABELS } from "../components/requests/QuotePanel";
import {
  ArrowSquareOut, ChatCircleDots, Check, Crown, DownloadSimple, FilePdf, LockSimple, Paperclip, SignOut, Star, SuitcaseRolling, Translate, WhatsappLogo,
} from "../components/Icon";
import { moneyText } from "../components/Money";
import { pageVars } from "../components/storefront/style";
import { ErrorBox, Loading } from "../components/ui";
import { useI18n } from "../lang";
import { pinTheme } from "../themeMode";
import type { PublicCompany, ServicePart } from "../types";
import { dateTime, shortDate } from "../util";

interface Me { name: string | null; phone: string | null; company_name: string;
  member: { key: string; name_en: string; name_ar: string; perks_en: string[]; perks_ar: string[]; since: string | null } | null }
interface Trip {
  id: number; reference: string; title: string; departure_date: string | null; end_date: string | null; adults: number; children: number;
  total_price: number; currency: string; status: string; phase: "quotation" | "booking" | "upcoming" | "travelling" | "finished" | "cancelled";
  steps: { action: string; at: string }[]; rating: number | null; comment: string | null; can_rate: boolean;
  service_en: string | null; service_ar: string | null;
  choices: { number: number; part: ServicePart; title: string; provider: string | null; link: string | null; details: string | null; price: number | null; chosen: boolean }[];
  payment_info: { en: string; ar: string } | null;
  checklist: { label_en: string; label_ar: string; done: boolean }[];
  files: { key: string; name: string; kind: string; size: number; content_type: string; at: string }[];
  can_upload: boolean; upload_is_proof: boolean; has_quotation: boolean;
  documents: { key: string; label_en: string; label_ar: string; required: boolean; need: number; have: number; done: boolean }[];
  paid: number | null; balance: number | null; receipts_waiting: number;
  itinerary: { day: number; title: string; details: string; date?: string }[];
  /** The request's steps (names and progress) and what to pay now. */
  progress: { label_en: string; label_ar: string; state: "pending" | "active" | "done" | "skipped" }[];
  due_now: number | null;
}
interface Chat { id: number; channel: string; created_at: string; last_message_at: string; messages: { sender: string; content: string; created_at: string }[] }

const PHASE: Record<Trip["phase"], string> = {
  quotation: "Quotation", booking: "In progress", upcoming: "Upcoming", travelling: "Travelling now", finished: "Finished", cancelled: "Cancelled",
};
const TRACK = ["Requested", "Paid", "Confirmed", "Travelling", "Back home"];
// Where the quotation is, in the client's words.
const QUOTE_TEXT: Record<string, string> = {
  new: "We are preparing your choices.", quoted: "Your choices are ready: answer us in the chat.",
  changes: "We are updating your choices.", chosen: "We are preparing your final quotation.",
  final: "Your final quotation is ready: approve it in the chat.",
};

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
  const [reference, setReference] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wa = company.whatsapp_number ? `https://wa.me/${company.whatsapp_number.replace(/\D/g, "")}?text=${encodeURIComponent("My trips")}` : null;
  const send = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await post(`/api/public/companies/${slug}/me/code`, { phone, reference: reference.trim() }, { customerToken: null }); setSent(true); }
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
      {!sent && <p className="mt-muted mt-small">{t("Write the request ID from our messages (it starts with TRV-) and the WhatsApp number you gave us. We send a code to that WhatsApp.")}</p>}
      {!sent ? (
        <form onSubmit={send} className="mt-form">
          <label htmlFor="mt-ref">{t("Your request ID")}</label>
          <input id="mt-ref" value={reference} onChange={(e) => setReference(e.target.value.toUpperCase().slice(0, 20))} dir="ltr"
            placeholder="TRV-AB12CD" required minLength={6} autoComplete="off" />
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

function TripCard({ trip, onRate, slug, token, onTrips }: {
  trip: Trip; onRate: (id: number, rating: number, comment: string) => Promise<void>;
  slug: string; token: string; onTrips: (trips: Trip[]) => void;
}) {
  const { t, lang } = useI18n();
  const [uploading, setUploading] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const upload = async (e: ChangeEvent<HTMLInputElement>, purpose: "proof" | "document" | "auto" = "auto", requirement: string | null = null) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setFileError(null);
    if (file.size > 6_000_000) { setFileError(t("The file is too large (maximum 6 MB)")); return; }
    setUploading(true);
    try {
      const data = await readFileBase64(file);
      onTrips(await post<Trip[]>(`/api/public/companies/${slug}/me/trips/${trip.id}/files`,
        { name: file.name, content_type: file.type, data_base64: data, purpose, requirement }, { customerToken: token }));
    } catch (err) { setFileError((err as Error).message); } finally { setUploading(false); }
  };
  const parts = [...new Set(trip.choices.map((c) => c.part))];
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
        {trip.total_price > 0 && <strong>{moneyText(trip.total_price, trip.currency, lang)}</strong>}
      </div>
      {(trip.service_en || trip.service_ar) && <div className="mt-service">{lang === "ar" ? trip.service_ar || trip.service_en : trip.service_en}</div>}
      {trip.phase === "quotation" && QUOTE_TEXT[trip.status] && <p className="mt-muted">{t(QUOTE_TEXT[trip.status])}</p>}
      {trip.choices.length > 0 && (
        <div className="mt-choices">
          {parts.map((p) => (
            <div key={p}>
              <div className="mt-choices-part">{t(PART_LABELS[p] ?? "Other")}</div>
              <ul>
                {trip.choices.filter((c) => c.part === p).map((c) => (
                  <li key={c.number} className={c.chosen ? "chosen" : ""}>
                    <span className="mt-choice-n">{c.number}</span>
                    <span className="mt-choice-main">
                      <strong dir="auto">{c.title}</strong>{c.provider && <span className="mt-muted"> · {c.provider}</span>}
                      {c.link && <a href={c.link} target="_blank" rel="noreferrer noopener" aria-label={t("Open link")}> <ArrowSquareOut /></a>}
                      {c.details && <span className="mt-muted mt-small" dir="auto">{c.details}</span>}
                    </span>
                    {c.price !== null && <strong className="mt-choice-price">{moneyText(c.price, trip.currency, lang)}</strong>}
                    {c.chosen && <Check className="mt-choice-ok" aria-label={t("Your choice")} />}
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {trip.status === "quoted" && <p className="mt-muted mt-small">{t("Reply in our chat with the number of your choice for each part, or tell us what to change.")}</p>}
        </div>
      )}
      {trip.has_quotation && (
        <Link className="mt-quote-link" to={`/c/${slug}/me/quotation/${trip.id}`}><FilePdf />{t("View your quotation (with photos, printable)")}</Link>
      )}
      {trip.payment_info && (trip.payment_info.en || trip.payment_info.ar) && (
        <div className="mt-pay">
          <div className="mt-choices-part">{t("How to pay")}</div>
          <p dir="auto">{lang === "ar" ? trip.payment_info.ar || trip.payment_info.en : trip.payment_info.en || trip.payment_info.ar}</p>
        </div>
      )}
      {trip.due_now != null && trip.due_now > 0 && trip.receipts_waiting === 0 && (
        <p className="mt-due">{t("To pay now: {v}", { v: moneyText(trip.due_now, trip.currency, lang) })}</p>
      )}
      {trip.paid != null && (trip.paid > 0 || trip.receipts_waiting > 0) && (
        <p className="mt-muted">{t("Paid: {paid}", { paid: moneyText(trip.paid, trip.currency, lang) })}
          {(trip.balance ?? 0) > 0 && ` · ${t("Left to pay: {v}", { v: moneyText(trip.balance ?? 0, trip.currency, lang) })}`}
          {trip.receipts_waiting > 0 && ` · ${t("We are checking your receipt.")}`}</p>
      )}
      {trip.can_upload && trip.upload_is_proof && (
        <label className="mt-upload proof">
          <Paperclip />
          <span>{uploading ? t("Sending…") : t("Send your transfer receipt (photo or PDF)")}</span>
          <input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" hidden disabled={uploading} onChange={(e) => upload(e, "proof")} />
        </label>
      )}
      {trip.documents.length > 0 && trip.can_upload && (
        <div className="mt-docs">
          <div className="mt-choices-part">{t("Documents we need from you")}</div>
          <ul>
            {trip.documents.map((d) => (
              <li key={d.key} className={d.done ? "done" : ""}>
                <span className="mt-doc-state">{d.done ? <Check /> : `${d.have}/${d.need}`}</span>
                <span className="mt-doc-name">{lang === "ar" ? d.label_ar || d.label_en : d.label_en}{!d.required && <span className="mt-muted mt-small"> · {t("optional")}</span>}
                  {d.need > 1 && !d.done && <span className="mt-muted mt-small"> · {t("one for each traveller")}</span>}</span>
                <label className="mt-doc-btn"><Paperclip /> {d.have ? t("Add") : t("Send")}
                  <input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" hidden disabled={uploading} onChange={(e) => upload(e, "document", d.key)} />
                </label>
              </li>
            ))}
          </ul>
        </div>
      )}
      {trip.itinerary.length > 0 && (
        <details className="mt-plan">
          <summary>{t("Your day-by-day plan ({n} days)", { n: trip.itinerary.length })}</summary>
          <ol>
            {trip.itinerary.map((d) => (
              <li key={d.day}><strong>{t("Day {n}", { n: d.day })}{d.date ? ` · ${shortDate(d.date)}` : ""}: <span dir="auto">{d.title}</span></strong>
                {d.details && <p dir="auto">{d.details}</p>}</li>
            ))}
          </ol>
        </details>
      )}
      <ErrorBox error={fileError} />
      {trip.checklist.length > 0 && (
        <ul className="mt-checklist" aria-label={t("Booking steps")}>
          {trip.checklist.map((c, i) => (
            <li key={i} className={c.done ? "done" : ""}><span>{c.done ? <Check /> : i + 1}</span>{lang === "ar" ? c.label_ar || c.label_en : c.label_en}</li>
          ))}
        </ul>
      )}
      {trip.files.length > 0 && (
        <ul className="mt-files" aria-label={t("Files")}>
          {trip.files.map((f) => (
            <li key={f.key}>
              <span dir="auto">{f.name}</span>
              <span className="mt-muted mt-small">{f.kind === "document" ? t("From us") : t("You sent it")}</span>
              <button type="button" className="mt-file-btn" aria-label={t("Download {name}", { name: f.name })}
                onClick={() => download(`/api/public/companies/${slug}/me/files/${f.key}`, f.name, { customerToken: token })
                  .catch((err) => setFileError((err as Error).message))}><DownloadSimple /></button>
            </li>
          ))}
        </ul>
      )}
      {trip.phase !== "cancelled" && trip.progress?.length > 0 && (
        <ol className="mt-track mt-track-flow" aria-label={t("Trip progress")}>
          {trip.progress.map((s, i) => (
            <li key={i} className={s.state === "done" || s.state === "skipped" ? "done" : s.state === "active" ? "now" : ""} aria-current={s.state === "active" ? "step" : undefined}>
              <span>{s.state === "done" ? <Check /> : i + 1}</span>{lang === "ar" ? s.label_ar : s.label_en}
            </li>
          ))}
        </ol>
      )}
      {trip.phase !== "cancelled" && !trip.progress?.length && (
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
  const [tab, setTab] = useState<"trips" | "chats">("trips");
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
    Promise.all([get<Me>(base, o), get<Trip[]>(`${base}/trips`, o), get<Chat[]>(`${base}/chats`, o)])
      .then(([m, tr, ch]) => { setMe(m); setTrips(tr); setChats(ch); setError(null); })
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
  const upcoming = trips.filter((x) => ["quotation", "booking", "upcoming", "travelling"].includes(x.phase));
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
            </div>
            {tab === "trips" && (trips.length === 0 ? <p className="mt-muted">{t("No bookings yet. Ask us in the chat and we'll plan your next trip.")}</p> : (<>
              {upcoming.length > 0 && <h2 className="mt-h2">{t("Current and upcoming")}</h2>}
              {upcoming.map((x) => <TripCard key={x.id} trip={x} onRate={rate} slug={slug} token={token} onTrips={setTrips} />)}
              {past.length > 0 && <h2 className="mt-h2">{t("Past trips")}</h2>}
              {past.map((x) => <TripCard key={x.id} trip={x} onRate={rate} slug={slug} token={token} onTrips={setTrips} />)}
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
            
            <p className="mt-muted mt-small mt-foot">
              <LockSimple /> {t("This page is private to you.")} <button type="button" className="link-btn" onClick={everywhere}>{t("Sign out on all devices")}</button>
            </p>
          </>)}
      </main>
    </div>
  );
}
