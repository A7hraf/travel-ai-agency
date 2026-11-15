import { FormEvent, useEffect, useState } from "react";
import { api, get, post, put } from "../../api";
import ImageUpload from "../ImageUpload";
import { useAuth } from "../../auth";
import { useI18n } from "../../lang";
import type { ServicePart, Ticket, TicketOption } from "../../types";
import { ArrowSquareOut, BookmarkSimple, Check, FilePdf, PaperPlaneRight, PencilSimple, Plus, Sparkle, Star, Trash } from "../Icon";
import { moneyText } from "../Money";
import { ErrorBox } from "../ui";

export const PARTS: ServicePart[] = ["flight", "hotel", "transport", "activity", "food", "visa", "insurance", "other"];
export const PART_LABELS: Record<ServicePart, string> = {
  flight: "Flight", hotel: "Hotel", transport: "Transport", activity: "Activities", food: "Food", visa: "Visa",
  insurance: "Insurance", other: "Other",
};
const EDITABLE = ["new", "changes", "chosen"];

type Draft = { category: ServicePart; title: string; provider: string; link: string; details: string; cost_price: string; price: string;
  image_url: string | null; supplier_id: number | null };
type Margins = Record<string, { margin_pct: number; samples: number }>;
type LibItem = { id: number; name: string; place: string; stars: number | null; usual_price: number | string | null; preferred: boolean };
const blank = (part: ServicePart): Draft => ({ category: part, title: "", provider: "", link: "", details: "", cost_price: "", price: "",
  image_url: null, supplier_id: null });
const fromOption = (o: TicketOption): Draft => ({ category: o.category, title: o.title, provider: o.provider ?? "", link: o.link ?? "",
  details: o.details ?? "", cost_price: o.cost_price == null ? "" : String(o.cost_price), price: o.price == null ? "" : String(o.price),
  image_url: o.image_url, supplier_id: o.supplier_id });
const body = (d: Draft) => ({ ...d, provider: d.provider || null, link: d.link || null, details: d.details || null,
  cost_price: d.cost_price === "" ? null : d.cost_price, price: d.price === "" ? null : d.price });

function OptionForm({ parts, initial, onSave, onCancel, margins }: {
  parts: ServicePart[]; initial: Draft; onSave: (d: Draft) => Promise<void>; onCancel?: () => void; margins?: Margins | null;
}) {
  const { t } = useI18n();
  const [d, setD] = useState(initial);
  const usual = margins?.[d.category];
  const cost = Number(d.cost_price);
  const suggested = usual && d.cost_price !== "" && cost > 0 ? (cost * (1 + usual.margin_pct / 100)).toFixed(3) : null;
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try { await onSave(d); if (!onCancel) setD(blank(d.category)); } catch { /* shown by the panel */ } finally { setBusy(false); }
  };
  return (
    <form className="gx-rq-opt-form" onSubmit={submit}>
      <select value={d.category} onChange={(e) => setD({ ...d, category: e.target.value as ServicePart })} aria-label={t("Part")}>
        {parts.map((p) => <option key={p} value={p}>{t(PART_LABELS[p])}</option>)}
      </select>
      <input value={d.title} onChange={(e) => setD({ ...d, title: e.target.value })} required minLength={2} maxLength={200} dir="auto"
        placeholder={t("Title (e.g. WY 601 Business, 08:10)")} aria-label={t("Title")} />
      <input value={d.provider} onChange={(e) => setD({ ...d, provider: e.target.value })} maxLength={120} dir="auto"
        placeholder={t("Airline / hotel / operator")} aria-label={t("Provider")} />
      <input value={d.link} onChange={(e) => setD({ ...d, link: e.target.value })} maxLength={500} dir="ltr" type="url"
        placeholder={t("Link (Booking.com, airline, activity page)")} aria-label={t("Link")} />
      <input value={d.cost_price} onChange={(e) => setD({ ...d, cost_price: e.target.value })} inputMode="decimal" dir="ltr"
        placeholder={t("Your cost")} aria-label={t("Your cost")} />
      <input value={d.price} onChange={(e) => setD({ ...d, price: e.target.value })} inputMode="decimal" dir="ltr"
        placeholder={t("Client price")} aria-label={t("Client price")} />
      {suggested && d.price === "" && (
        <button type="button" className="btn btn-sm btn-ghost gx-rq-margin" onClick={() => setD({ ...d, price: suggested })}>
          {t("Use your usual margin ({p}%): {v}", { p: usual!.margin_pct, v: suggested })}
        </button>
      )}
      <textarea value={d.details} onChange={(e) => setD({ ...d, details: e.target.value })} rows={2} maxLength={2000} dir="auto"
        placeholder={t("Details for the client (times, room type, conditions…)")} aria-label={t("Details")} />
      <div className="gx-rq-photo"><ImageUpload value={d.image_url} onChange={(url) => setD({ ...d, image_url: url })} label={t("Photo for the quotation (optional)")} maxSide={1200} /></div>
      <div className="gx-rq-opt-form-actions">
        {onCancel && <button type="button" className="btn btn-sm btn-ghost" onClick={onCancel}>{t("Cancel")}</button>}
        <button className="btn btn-sm btn-soft" disabled={busy}>{onCancel ? <><Check />{t("Save")}</> : <><Plus />{t("Add choice")}</>}</button>
      </div>
    </form>
  );
}

/** The quotation of a request: up to 3 choices per part, the AI's drafts, the final quotation, and the client's
 *  answers written down by staff. */
export default function QuotePanel({ ticket, onChange }: { ticket: Ticket; onChange: (t: Ticket) => void }) {
  const { t, lang } = useI18n();
  const { user, can } = useAuth();
  const [picked, setPicked] = useState<number[]>(ticket.options.filter((o) => o.sent_to_client).map((o) => o.id));
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [total, setTotal] = useState("");
  const [note, setNote] = useState("");
  const [answer, setAnswer] = useState("");
  const [answerNote, setAnswerNote] = useState("");
  // The client's pick, one per part, when staff write down an answer given by phone.
  const [clientPick, setClientPick] = useState<Record<string, number>>({});
  const [lib, setLib] = useState<Record<string, LibItem[]>>({});
  const [margins, setMargins] = useState<Margins | null>(null);
  const addons = user?.company?.addons ?? [];
  const library = addons.includes("library");
  const isEditable = can("tickets.manage") && EDITABLE.includes(ticket.status) && !!ticket.service && ticket.service.key !== "packages";
  useEffect(() => {
    if (!isEditable) return;
    if (library) get<Record<string, LibItem[]>>(`/api/tickets/${ticket.id}/library`).then(setLib).catch(() => {});
    if (addons.includes("library_margins")) get<Margins>("/api/library/margins").then(setMargins).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticket.id, isEditable, library]);
  if (!ticket.service || ticket.service.key === "packages") return null;
  const base = `/api/tickets/${ticket.id}`;
  const manage = can("tickets.manage");
  const editable = manage && EDITABLE.includes(ticket.status);
  const planner = !!user?.company?.addons?.includes("trip_planner");
  const parts = (ticket.parts && ticket.parts.length ? ticket.parts : PARTS) as ServicePart[];
  const cur = ticket.currency;
  const m = (v: number | null) => (v == null ? "—" : moneyText(Number(v), cur, lang));
  const chosen = ticket.options.filter((o) => o.chosen);
  const chosenTotal = chosen.reduce((s, o) => s + Number(o.price ?? 0), 0);
  const picking = manage && ticket.status === "quoted" && answer === "choose";
  const tooMany = PARTS.some((p) => ticket.options.filter((o) => o.category === p && picked.includes(o.id)).length > 3);

  const run = async (fn: () => Promise<Ticket>) => {
    setBusy(true);
    setError(null);
    try { const tk = await fn(); onChange(tk); setPicked(tk.options.filter((o) => o.sent_to_client).map((o) => o.id)); }
    catch (e) { setError((e as Error).message); throw e; } finally { setBusy(false); }
  };
  const safe = (fn: () => Promise<Ticket>) => { run(fn).catch(() => {}); };

  return (
    <section className="gx-rq-quote" aria-label={t("Quotation")}>
      <div className="gx-rq-quote-head">
        <h3>{t("Quotation")}</h3>
        {addons.includes("quotes") && ticket.options.some((o) => o.price != null) && (
          <span className="gx-rq-pdf">
            <a className="btn btn-sm btn-ghost" href={`/app/tickets/${ticket.id}/quotation?kind=draft`} target="_blank" rel="noreferrer"><FilePdf />{t("Quotation PDF")}</a>
            {ticket.options.some((o) => o.chosen) && (
              <a className="btn btn-sm btn-ghost" href={`/app/tickets/${ticket.id}/quotation?kind=final`} target="_blank" rel="noreferrer"><FilePdf />{t("Final PDF")}</a>
            )}
          </span>
        )}
        {editable && planner && parts.some((p) => p !== "other") && (
          <button type="button" className="btn btn-sm btn-soft" disabled={busy} onClick={() => safe(() => post<Ticket>(`${base}/ai-draft`))}>
            <Sparkle weight="fill" />{busy ? t("The AI is searching…") : t("Draft choices with AI")}
          </button>
        )}
      </div>
      {editable && <p className="muted small">{t("Tick up to 3 choices per part. Every choice sent needs its client price; AI estimates are for you only.")}</p>}
      {ticket.options.length === 0 && <p className="muted small">{t("No choices yet.")}</p>}
      {PARTS.filter((p) => ticket.options.some((o) => o.category === p)).map((p) => (
        <div key={p} className="gx-rq-part">
          <div className="gx-rq-part-head"><strong>{t(PART_LABELS[p])}</strong>
            {editable && <span className="muted small">{ticket.options.filter((o) => o.category === p && picked.includes(o.id)).length} / 3</span>}</div>
          {ticket.options.filter((o) => o.category === p).map((o) => editing === o.id ? (
            <OptionForm key={o.id} parts={parts} initial={fromOption(o)} onCancel={() => setEditing(null)} margins={margins}
              onSave={(d) => run(() => put<Ticket>(`${base}/options/${o.id}`, body(d))).then(() => setEditing(null))} />
          ) : (
            <div key={o.id} className={`gx-rq-opt ${o.chosen ? "chosen" : ""}`}>
              {editable && <input type="checkbox" checked={picked.includes(o.id)} aria-label={t("Send {name}", { name: o.title })}
                onChange={() => setPicked(picked.includes(o.id) ? picked.filter((x) => x !== o.id) : [...picked, o.id])} />}
              {picking && o.sent_to_client && <input type="radio" name={`pick-${ticket.id}-${o.category}`} checked={clientPick[o.category] === o.id}
                aria-label={t("The client picked {name}", { name: o.title })} onChange={() => setClientPick({ ...clientPick, [o.category]: o.id })} />}
              {o.image_url && <img src={o.image_url} alt="" className="gx-rq-opt-img" />}
              <div className="gx-rq-opt-main">
                <div><strong dir="auto">{o.title}</strong>{o.provider && <span className="muted"> · {o.provider}</span>}
                  {o.link && <a href={o.link} target="_blank" rel="noreferrer noopener" className="gx-rq-link" aria-label={t("Open link")}><ArrowSquareOut /></a>}</div>
                {o.details && <div className="muted small" dir="auto">{o.details}</div>}
                {o.ai_reason && <div className="muted small gx-rq-why" dir="auto"><Sparkle weight="fill" /> {o.ai_reason}</div>}
                <div className="small">
                  {[o.added_by === "ai" && <span key="ai" className="gx-ai-tag">{t("AI suggestion")}</span>,
                    o.sent_to_client && <span key="sent" className="muted">{t("sent")}</span>,
                    o.chosen && <strong key="chosen" className="gx-rq-chosen">{t("chosen by the client")}</strong>]
                    .filter(Boolean).flatMap((x, i) => (i ? [<span key={`s${i}`} className="muted"> · </span>, x] : [x]))}
                </div>
              </div>
              <div className="gx-rq-opt-prices">
                {o.price != null ? <strong>{m(o.price)}</strong>
                  : o.estimate_price != null ? <span className="muted" title={t("AI estimate: set the real price before sending")}>{t("AI est.")} ≈ {m(o.estimate_price)}</span>
                    : <span className="muted">{t("No price")}</span>}
                {o.cost_price != null && <span className="muted small">{t("Cost")} {m(o.cost_price)}</span>}
                {o.cost_price != null && o.price != null && (
                  <span className={`small gx-rq-profit ${Number(o.price) - Number(o.cost_price) < 0 ? "neg" : ""}`}>{t("Profit")} {m(Number(o.price) - Number(o.cost_price))}</span>
                )}
              </div>
              {manage && library && !o.supplier_id && (
                <button type="button" className="icon-btn" aria-label={t("Save to the library")} title={t("Save to the library")}
                  onClick={() => safe(() => post<Ticket>(`${base}/options/${o.id}/save-to-library`))}><BookmarkSimple /></button>
              )}
              {editable && <button type="button" className="icon-btn" aria-label={t("Edit")} onClick={() => setEditing(o.id)}><PencilSimple /></button>}
              {editable && <button type="button" className="icon-btn" aria-label={t("Remove")} onClick={() => safe(() => api<Ticket>("DELETE", `${base}/options/${o.id}`))}><Trash /></button>}
            </div>
          ))}
        </div>
      ))}
      {editable && Object.keys(lib).length > 0 && (
        <div className="gx-rq-lib">
          <span className="muted small">{t("From your library:")}</span>
          {Object.entries(lib).flatMap(([p, items]) => items.filter((x) => !ticket.options.some((o) => o.supplier_id === x.id)).map((x) => (
            <button key={x.id} type="button" className="gx-chip" disabled={busy}
              onClick={() => safe(() => post<Ticket>(`${base}/options/from-library`, { supplier_id: x.id }))}>
              <Plus /> {t(PART_LABELS[p as ServicePart] ?? "Other")}: <bdi>{x.name}</bdi>{x.stars ? ` ${x.stars}★` : ""}
              {x.usual_price != null && ` · ${m(Number(x.usual_price))}`}{x.preferred && <Star weight="fill" />}
            </button>
          )))}
        </div>
      )}
      {editable && <OptionForm parts={parts} initial={blank(parts[0])} margins={margins} onSave={(d) => run(() => post<Ticket>(`${base}/options`, body(d)))} />}
      {editable && (
        <button type="button" className="btn btn-primary gx-rq-send" disabled={busy || !picked.length || tooMany}
          onClick={() => safe(() => post<Ticket>(`${base}/send-choices`, { option_ids: picked }))}>
          <PaperPlaneRight className="flip" />{t("Send {n} choices to the client", { n: picked.length })}
        </button>
      )}

      {manage && (ticket.status === "chosen" || ticket.status === "changes" || (ticket.status === "new" && ticket.service.pricing === "fixed")) && (
        <form className="gx-rq-final" onSubmit={(e) => { e.preventDefault(); safe(() => post<Ticket>(`${base}/send-final`, { total: total || null, note: note || null })); }}>
          <h4>{t("Final quotation")}</h4>
          {chosen.length > 0 && <ul className="gx-rq-final-list">{chosen.map((o) => <li key={o.id} dir="auto">{o.title} · {m(o.price)}</li>)}</ul>}
          <div className="gx-rq-row">
            <input value={total} onChange={(e) => setTotal(e.target.value)} inputMode="decimal" dir="ltr" aria-label={t("Final total")}
              placeholder={chosen.length ? `${t("Total")}: ${chosenTotal}` : t("Final total")} />
            <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} dir="auto" aria-label={t("Note for the client")}
              placeholder={t("Note for the client (optional)")} />
          </div>
          <button className="btn btn-primary" disabled={busy}><PaperPlaneRight className="flip" />{t("Send the final quotation")}</button>
        </form>
      )}

      {manage && ["quoted", "final", "pending_payment"].includes(ticket.status) && (
        <form className="gx-rq-answer" onSubmit={(e) => {
          e.preventDefault();
          if (!answer) return;
          const ids = answer === "choose" ? Object.values(clientPick) : [];
          safe(() => post<Ticket>(`${base}/client-answer`, { action: answer, option_ids: ids, note: answerNote || null, transfer_reference: answerNote || null }));
        }}>
          <h4>{t("The client answered by phone or in person?")}</h4>
          <div className="gx-rq-row">
            <select value={answer} onChange={(e) => setAnswer(e.target.value)} aria-label={t("The client's answer")}>
              <option value="">{t("Choose the answer")}</option>
              {ticket.status === "quoted" && <option value="choose">{t("Picked choices (mark them above)")}</option>}
              {ticket.status !== "pending_payment" && <option value="changes">{t("Asked for changes")}</option>}
              {ticket.status === "final" && <option value="approve">{t("Approved the final quotation")}</option>}
              {ticket.status !== "pending_payment" && <option value="reject">{t("Rejected")}</option>}
              {ticket.status === "pending_payment" && <option value="paid">{t("Paid (transfer number below)")}</option>}
              <option value="cancel">{t("Cancelled the request")}</option>
            </select>
            <input value={answerNote} onChange={(e) => setAnswerNote(e.target.value)} maxLength={2000} dir="auto"
              placeholder={answer === "paid" ? t("Transfer or receipt number") : t("What the client said")} aria-label={t("What the client said")} />
          </div>
          <button className="btn btn-soft" disabled={busy || !answer}>{t("Save the client's answer")}</button>
        </form>
      )}
      <ErrorBox error={error} />
    </section>
  );
}
