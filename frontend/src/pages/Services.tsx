import { FormEvent, useEffect, useState } from "react";
import { api, get, post, put } from "../api";
import { useAuth } from "../auth";
import { PageTitle, Switch } from "../components/admin/AdminUI";
import { ArrowDown, ArrowUp, Plus, Sparkle, Trash } from "../components/Icon";
import { PART_LABELS, PARTS } from "../components/requests/QuotePanel";
import { ErrorBox, Field, Loading } from "../components/ui";
import { useI18n } from "../lang";
import WorkflowEditor, { STEP_LABEL, stepBody, workflowProblems } from "../components/workflow/WorkflowEditor";
import type { Service, ServiceField, ServicePart, ServiceStep, WorkflowStep } from "../types";

/** workflow null: the built-in default steps (saved as such). */
type Draft = Omit<Service, "id" | "key" | "position" | "workflow" | "workflow_custom"> & { workflow: WorkflowStep[] | null };
const st = (type: WorkflowStep["type"], label_en: string, label_ar: string): WorkflowStep => ({ key: type, type, label_en, label_ar });
// The server's default for a new service (workflow.py GENERIC).
const NEW_SERVICE_STEPS: WorkflowStep[] = [
  st("intake", "Request details", "تفاصيل الطلب"), st("review", "Team review", "مراجعة الفريق"), st("quote", "Quotation", "عرض السعر"),
  st("documents", "Client documents", "مستندات العميل"), { ...st("payment", "Payment", "الدفع"), pay_mode: "rest" },
  st("booking", "Booking", "الحجز"), st("delivery", "Travel documents", "وثائق السفر"), st("feedback", "Feedback", "التقييم"),
];
const FIELD_TYPES = ["text", "long_text", "number", "date", "choice", "phone", "email"] as const;
const TYPE_LABELS: Record<string, string> = {
  text: "Short text", long_text: "Long text", number: "Number", date: "Date", choice: "Choice", phone: "Phone", email: "Email",
};
const PRICING_LABELS: Record<string, string> = {
  fixed: "Fixed price", dynamic: "Priced per request (quotation)", packages: "Ready-made packages",
};

const empty = (): Draft => ({
  name_en: "", name_ar: "", description_en: "", description_ar: "", pricing: "dynamic", price: null, price_note: "",
  parts: [], fields: [
    { key: "full_name", label_en: "Full name", label_ar: "الاسم الكامل", type: "text", required: true, choices: [] },
    { key: "phone", label_en: "WhatsApp number", label_ar: "رقم واتساب", type: "phone", required: true, choices: [] },
  ], steps: [], documents: [], rules: "", is_active: true, workflow: NEW_SERVICE_STEPS.map((x) => ({ ...x })),
});
const toDraft = (s: Service | Draft): Draft => ({
  name_en: s.name_en, name_ar: s.name_ar, description_en: s.description_en, description_ar: s.description_ar, pricing: s.pricing,
  price: s.price, price_note: s.price_note, parts: [...s.parts], fields: s.fields.map((f) => ({ ...f, choices: [...f.choices] })),
  steps: s.steps.map((x) => ({ ...x })), documents: (s.documents ?? []).map((x) => ({ ...x })), rules: s.rules, is_active: s.is_active,
  workflow: s.workflow ? s.workflow.map((x) => ({ ...x })) : null,
});
/** "Passport copy" → "passport_copy" (the key the AI and the answers use). */
const keyOf = (label: string, taken: string[]) => {
  let k = label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").replace(/^[0-9_]+/, "").slice(0, 36);
  if (k.length < 2) k = "item";
  let out = k;
  for (let i = 2; taken.includes(out); i++) out = `${k}_${i}`;
  return out;
};

function move<T>(list: T[], i: number, by: number): T[] {
  const j = i + by;
  if (j < 0 || j >= list.length) return list;
  const next = [...list];
  [next[i], next[j]] = [next[j], next[i]];
  return next;
}

function Editor({ initial, id, builtIn, custom, onSaved, onCancel, onDelete }: {
  initial: Draft; id: number | null; builtIn: boolean; custom?: boolean; onSaved: () => void; onCancel: () => void; onDelete?: () => void;
}) {
  const { t } = useI18n();
  const { user } = useAuth();
  const [d, setD] = useState<Draft>(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const packages = d.pricing === "packages";
  const setField = (i: number, f: Partial<ServiceField>) => setD({ ...d, fields: d.fields.map((x, j) => (j === i ? { ...x, ...f } : x)) });
  const setStep = (i: number, s: Partial<ServiceStep>) => setD({ ...d, steps: d.steps.map((x, j) => (j === i ? { ...x, ...s } : x)) });

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = { ...d, price: d.pricing === "fixed" && d.price !== null && d.price !== "" ? d.price : null,
      workflow: d.workflow ? d.workflow.map(stepBody) : null };
    try {
      if (id) await put(`/api/services/${id}`, body); else await post("/api/services", body);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="gx-card gx-svc-editor" onSubmit={save}>
      <div className="gx-grid-2">
        <Field label={t("Name (English)")}><input value={d.name_en} onChange={(e) => setD({ ...d, name_en: e.target.value })} required minLength={2} maxLength={120} dir="ltr" /></Field>
        <Field label={t("Name (Arabic)")}><input value={d.name_ar} onChange={(e) => setD({ ...d, name_ar: e.target.value })} required minLength={2} maxLength={120} dir="rtl" /></Field>
        <Field label={t("Description (English)")}><textarea rows={2} value={d.description_en} onChange={(e) => setD({ ...d, description_en: e.target.value })} maxLength={2000} dir="ltr" /></Field>
        <Field label={t("Description (Arabic)")}><textarea rows={2} value={d.description_ar} onChange={(e) => setD({ ...d, description_ar: e.target.value })} maxLength={2000} dir="rtl" /></Field>
      </div>

      {!packages && (
        <div className="gx-grid-2">
          <Field label={t("Price")}>
            <select value={d.pricing} onChange={(e) => setD({ ...d, pricing: e.target.value as Draft["pricing"] })}>
              <option value="dynamic">{t(PRICING_LABELS.dynamic)}</option>
              <option value="fixed">{t(PRICING_LABELS.fixed)}</option>
            </select>
          </Field>
          {d.pricing === "fixed" ? (
            <Field label={t("Fixed price")}><input value={d.price ?? ""} onChange={(e) => setD({ ...d, price: e.target.value })} inputMode="decimal" dir="ltr" required /></Field>
          ) : (
            <Field label={t("How the price is set")}><input value={d.price_note} onChange={(e) => setD({ ...d, price_note: e.target.value })} maxLength={1000} dir="auto"
              placeholder={t("e.g. flights at cost + 15 OMR per person")} /></Field>
          )}
        </div>
      )}
      {packages && <p className="muted small">{t("Clients book your ready-made packages directly: the price and seats come from the Packages page.")}</p>}

      {!packages && (
        <>
          <div className="gx-section-label">{t("What the quotation contains")}</div>
          <div className="gx-chips">
            {PARTS.map((p) => (
              <button key={p} type="button" className={`gx-chip ${d.parts.includes(p) ? "on" : ""}`} aria-pressed={d.parts.includes(p)}
                onClick={() => setD({ ...d, parts: d.parts.includes(p) ? d.parts.filter((x) => x !== p) : [...d.parts, p as ServicePart] })}>
                {t(PART_LABELS[p])}
              </button>
            ))}
          </div>
        </>
      )}

      <div className="gx-section-label">{t("Questions the AI asks the client")}</div>
      <div className="gx-svc-list">
        {d.fields.map((f, i) => (
          <div key={i} className="gx-svc-row">
            <input value={f.label_en} aria-label={t("Question (English)")} placeholder={t("Question (English)")} dir="ltr" required minLength={1} maxLength={120}
              onChange={(e) => setField(i, { label_en: e.target.value })} />
            <input value={f.label_ar} aria-label={t("Question (Arabic)")} placeholder={t("Question (Arabic)")} dir="rtl" required minLength={1} maxLength={120}
              onChange={(e) => setField(i, { label_ar: e.target.value })} />
            <select value={f.type} aria-label={t("Answer type")} onChange={(e) => setField(i, { type: e.target.value })}>
              {FIELD_TYPES.map((x) => <option key={x} value={x}>{t(TYPE_LABELS[x])}</option>)}
            </select>
            <label className="gx-svc-req"><input type="checkbox" checked={f.required} onChange={(e) => setField(i, { required: e.target.checked })} />{t("Required")}</label>
            <span className="gx-svc-btns">
              <button type="button" className="icon-btn" aria-label={t("Move up")} onClick={() => setD({ ...d, fields: move(d.fields, i, -1) })}><ArrowUp /></button>
              <button type="button" className="icon-btn" aria-label={t("Move down")} onClick={() => setD({ ...d, fields: move(d.fields, i, 1) })}><ArrowDown /></button>
              <button type="button" className="icon-btn" aria-label={t("Remove")} onClick={() => setD({ ...d, fields: d.fields.filter((_, j) => j !== i) })}><Trash /></button>
            </span>
            {f.type === "choice" && (
              <input className="gx-svc-wide" value={f.choices.join(", ")} aria-label={t("Choices, separated by commas")} placeholder={t("Choices, separated by commas")} dir="auto"
                onChange={(e) => setField(i, { choices: e.target.value.split(",").map((x) => x.trim()).filter(Boolean).slice(0, 20) })} />
            )}
          </div>
        ))}
      </div>
      <button type="button" className="btn btn-sm btn-ghost" disabled={d.fields.length >= 30}
        onClick={() => setD({ ...d, fields: [...d.fields, { key: keyOf(`question ${d.fields.length + 1}`, d.fields.map((x) => x.key)), label_en: "", label_ar: "", type: "text", required: true, choices: [] }] })}>
        <Plus />{t("Add a question")}
      </button>

      {!packages && (
        <>
          <div className="gx-section-label">{t("Booking checklist")}</div>
          <div className="gx-svc-list">
            {d.steps.map((s, i) => (
              <div key={i} className="gx-svc-row gx-svc-step">
                <input value={s.label_en} aria-label={t("Step (English)")} placeholder={t("Step (English)")} dir="ltr" required maxLength={120}
                  onChange={(e) => setStep(i, { label_en: e.target.value })} />
                <input value={s.label_ar} aria-label={t("Step (Arabic)")} placeholder={t("Step (Arabic)")} dir="rtl" required maxLength={120}
                  onChange={(e) => setStep(i, { label_ar: e.target.value })} />
                <span className="gx-svc-btns">
                  <button type="button" className="icon-btn" aria-label={t("Move up")} onClick={() => setD({ ...d, steps: move(d.steps, i, -1) })}><ArrowUp /></button>
                  <button type="button" className="icon-btn" aria-label={t("Move down")} onClick={() => setD({ ...d, steps: move(d.steps, i, 1) })}><ArrowDown /></button>
                  <button type="button" className="icon-btn" aria-label={t("Remove")} onClick={() => setD({ ...d, steps: d.steps.filter((_, j) => j !== i) })}><Trash /></button>
                </span>
              </div>
            ))}
          </div>
          <button type="button" className="btn btn-sm btn-ghost" disabled={d.steps.length >= 20}
            onClick={() => setD({ ...d, steps: [...d.steps, { key: keyOf(`step ${d.steps.length + 1}`, d.steps.map((x) => x.key)), label_en: "", label_ar: "" }] })}>
            <Plus />{t("Add a step")}
          </button>
        </>
      )}

      <div className="gx-section-label">{t("Documents the client sends")}</div>
      <p className="muted small">{t("Passport copies, photos, statements… The AI asks for them, the client sends them on WhatsApp or their trips page, and the request shows what is missing.")}</p>
      <div className="gx-svc-list">
        {d.documents.map((doc, i) => (
          <div key={i} className="gx-svc-row gx-svc-doc">
            <input value={doc.label_en} aria-label={t("Document (English)")} placeholder={t("Document (English)")} dir="ltr" required maxLength={80}
              onChange={(e) => setD({ ...d, documents: d.documents.map((x, j) => (j === i ? { ...x, label_en: e.target.value } : x)) })} />
            <input value={doc.label_ar} aria-label={t("Document (Arabic)")} placeholder={t("Document (Arabic)")} dir="rtl" required maxLength={80}
              onChange={(e) => setD({ ...d, documents: d.documents.map((x, j) => (j === i ? { ...x, label_ar: e.target.value } : x)) })} />
            <label className="gx-svc-req"><input type="checkbox" checked={doc.required}
              onChange={(e) => setD({ ...d, documents: d.documents.map((x, j) => (j === i ? { ...x, required: e.target.checked } : x)) })} />{t("Required")}</label>
            <label className="gx-svc-req"><input type="checkbox" checked={doc.per_traveller}
              onChange={(e) => setD({ ...d, documents: d.documents.map((x, j) => (j === i ? { ...x, per_traveller: e.target.checked } : x)) })} />{t("One per traveller")}</label>
            <button type="button" className="icon-btn" aria-label={t("Remove")} onClick={() => setD({ ...d, documents: d.documents.filter((_, j) => j !== i) })}><Trash /></button>
          </div>
        ))}
      </div>
      <button type="button" className="btn btn-sm btn-ghost" disabled={d.documents.length >= 15}
        onClick={() => setD({ ...d, documents: [...d.documents, { key: keyOf(`document ${d.documents.length + 1}`, d.documents.map((x) => x.key)), label_en: "", label_ar: "", required: true, per_traveller: false }] })}>
        <Plus />{t("Add a document")}
      </button>

      <div className="gx-section-label">{t("Steps of each request")}</div>
      <p className="muted small">{t("Every new request of this service follows these steps, in this order. The team can still change the steps of one request.")}</p>
      {d.workflow ? (
        <WorkflowEditor steps={d.workflow} onChange={(w) => setD({ ...d, workflow: w })} currency={user?.company?.currency ?? "OMR"} />
      ) : <p className="muted small">{t("The default steps will be used.")}</p>}
      {builtIn && custom && d.workflow && (
        <button type="button" className="btn btn-sm btn-ghost" onClick={() => setD({ ...d, workflow: null })}>{t("Use the default steps again")}</button>
      )}

      <Field label={t("Rules and exceptions (the AI follows them)")}>
        <textarea rows={3} value={d.rules} onChange={(e) => setD({ ...d, rules: e.target.value })} maxLength={4000} dir="auto"
          placeholder={t("e.g. Visa requests need 10 working days. No refunds after the visa is issued.")} />
      </Field>
      <Switch checked={d.is_active} onChange={(v) => setD({ ...d, is_active: v })} label={t("Offered to clients")}
        hint={t("Switched off, the AI no longer offers it. Old requests stay.")} />
      <ErrorBox error={error} />
      <div className="gx-form-actions">
        {id && !builtIn && onDelete && <button type="button" className="btn btn-ghost btn-danger-text" onClick={onDelete}><Trash />{t("Delete")}</button>}
        <button type="button" className="btn btn-ghost" onClick={onCancel}>{t("Cancel")}</button>
        <button className="btn btn-primary" disabled={busy || (!!d.workflow && workflowProblems(d.workflow).length > 0)}>{busy ? t("Saving…") : t("Save the service")}</button>
      </div>
    </form>
  );
}

/** How long each step may take before a request counts as late (company admins). */
function SlaCard() {
  const { t, lang } = useI18n();
  const [hours, setHours] = useState<Record<string, string> | null>(null);
  const [defaults, setDefaults] = useState<Record<string, number>>({});
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    get<{ defaults: Record<string, number>; hours: Record<string, number> }>("/api/tickets/sla")
      .then((r) => { setDefaults(r.defaults); setHours(Object.fromEntries(Object.entries(r.hours).map(([k, v]) => [k, String(v)]))); })
      .catch((e) => setError((e as Error).message));
  }, []);
  if (!hours) return error ? <ErrorBox error={error} /> : null;
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setError(null); setSaved(false);
    try {
      await put("/api/tickets/sla", { hours: Object.fromEntries(Object.entries(hours).map(([k, v]) => [k, Number(v) || defaults[k]])) });
      setSaved(true);
    } catch (err) { setError((err as Error).message); }
  };
  return (
    <form className="gx-card" onSubmit={save}>
      <div className="gx-section-label">{t("How long each step may take")}</div>
      <p className="muted small">{t("After this time a request counts as late: it shows in red, and the employee (or whoever assigns requests) is told once.")}</p>
      <div className="gx-sla">
        {Object.keys(defaults).map((k) => (
          <label key={k} className="gx-sla-row">
            <span>{lang === "ar" ? STEP_LABEL[k]?.ar : STEP_LABEL[k]?.en}</span>
            <input type="number" min={1} max={1440} value={hours[k] ?? ""} onChange={(e) => { setSaved(false); setHours({ ...hours, [k]: e.target.value }); }} dir="ltr" />
            <small className="muted">{t("hours")}</small>
          </label>
        ))}
      </div>
      <ErrorBox error={error} />
      <div className="gx-form-actions">{saved && <span className="muted small">{t("Saved.")}</span>}<button className="btn btn-primary btn-sm">{t("Save")}</button></div>
    </form>
  );
}

function PaymentCard() {
  const { t } = useI18n();
  const [info, setInfo] = useState<{ en: string; ar: string } | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { get<{ en: string; ar: string }>("/api/payment-info").then(setInfo).catch((e) => setError((e as Error).message)); }, []);
  if (!info) return error ? <ErrorBox error={error} /> : null;
  const save = (e: FormEvent) => {
    e.preventDefault();
    setSaved(false);
    put<{ en: string; ar: string }>("/api/payment-info", info).then((x) => { setInfo(x); setSaved(true); setError(null); })
      .catch((err) => setError((err as Error).message));
  };
  return (
    <form className="gx-card" onSubmit={save}>
      <div className="gx-card-title">{t("How clients pay")}</div>
      <p className="muted small">{t("Sent to the client when they approve the final quotation: bank name, account or IBAN, and what to write in the transfer.")}</p>
      <div className="gx-grid-2">
        <Field label={t("English")}><textarea rows={4} value={info.en} maxLength={1500} dir="ltr" onChange={(e) => { setInfo({ ...info, en: e.target.value }); setSaved(false); }} /></Field>
        <Field label={t("Arabic")}><textarea rows={4} value={info.ar} maxLength={1500} dir="rtl" onChange={(e) => { setInfo({ ...info, ar: e.target.value }); setSaved(false); }} /></Field>
      </div>
      <ErrorBox error={error} />
      <div className="gx-form-actions">{saved && <span className="muted small">{t("Saved.")}</span>}<button className="btn btn-primary">{t("Save")}</button></div>
    </form>
  );
}

interface QuoteDesign {
  intro_en: string; intro_ar: string; terms_en: string; terms_ar: string; footer_en: string; footer_ar: string; valid_days: number;
  reference_prefix: string; show_photos: boolean; show_item_prices: boolean; show_itinerary: boolean; show_terms: boolean; show_contact: boolean;
}
const QUOTE_PARTS: [keyof QuoteDesign, string][] = [
  ["show_photos", "Photos of hotels, flights and activities"], ["show_item_prices", "The price of each item on the final quotation"],
  ["show_itinerary", "The day-by-day plan"], ["show_terms", "Terms and conditions"], ["show_contact", "Your contacts"],
];

function QuoteDesignCard() {
  const { t } = useI18n();
  const [d, setD] = useState<QuoteDesign | null>(null);
  const [sample, setSample] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { get<QuoteDesign>("/api/quote-settings").then(setD).catch((e) => setError((e as Error).message)); }, []);
  if (!d) return error ? <ErrorBox error={error} /> : null;
  const set = (patch: Partial<QuoteDesign>) => { setD({ ...d, ...patch }); setSaved(false); };
  const read = async () => {
    setBusy(true); setError(null);
    try { setD(await post<QuoteDesign>("/api/quote-settings/ai-draft", { text: sample })); setSaved(false); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { setD(await put<QuoteDesign>("/api/quote-settings", d)); setSaved(true); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <form className="gx-card" onSubmit={save}>
      <div className="gx-card-title">{t("Quotation design")}</div>
      <p className="muted small">{t("Every quotation uses your logo and colours (Customer page design), and these texts. The AI fills in the trip, the choices, photos and prices.")}</p>
      <Field label={t("Paste a sample of your quotation (the AI keeps your introduction, terms and footer)")}>
        <textarea rows={3} value={sample} onChange={(e) => setSample(e.target.value)} maxLength={12000} dir="auto" />
      </Field>
      <div className="gx-form-actions"><button type="button" className="btn btn-soft" disabled={busy || sample.trim().length < 20} onClick={read}>
        <Sparkle weight="fill" />{busy ? t("The AI is reading…") : t("Read my sample")}</button></div>
      <div className="gx-grid-2">
        <Field label={t("Introduction (English)")}><textarea rows={3} value={d.intro_en} onChange={(e) => set({ intro_en: e.target.value })} maxLength={3000} dir="ltr" /></Field>
        <Field label={t("Introduction (Arabic)")}><textarea rows={3} value={d.intro_ar} onChange={(e) => set({ intro_ar: e.target.value })} maxLength={3000} dir="rtl" /></Field>
        <Field label={t("Terms and conditions (English)")}><textarea rows={4} value={d.terms_en} onChange={(e) => set({ terms_en: e.target.value })} maxLength={4000} dir="ltr" /></Field>
        <Field label={t("Terms and conditions (Arabic)")}><textarea rows={4} value={d.terms_ar} onChange={(e) => set({ terms_ar: e.target.value })} maxLength={4000} dir="rtl" /></Field>
        <Field label={t("Footer (English)")}><input value={d.footer_en} onChange={(e) => set({ footer_en: e.target.value })} maxLength={500} dir="ltr" /></Field>
        <Field label={t("Footer (Arabic)")}><input value={d.footer_ar} onChange={(e) => set({ footer_ar: e.target.value })} maxLength={500} dir="rtl" /></Field>
        <Field label={t("Valid for (days)")}><input type="number" min={1} max={90} value={d.valid_days} onChange={(e) => set({ valid_days: Number(e.target.value) || 7 })} dir="ltr" /></Field>
        <Field label={t("Before the reference")} hint={t("For example Q- gives Q-TRV-AB12CD")}>
          <input value={d.reference_prefix ?? ""} onChange={(e) => set({ reference_prefix: e.target.value.toUpperCase() })} maxLength={12} pattern="[A-Za-z0-9-]*" dir="ltr" />
        </Field>
      </div>
      <div className="gx-section-label">{t("What the quotation shows")}</div>
      <div className="gx-feat-opts">
        {QUOTE_PARTS.map(([k, label]) => (
          <Switch key={k} checked={d[k] !== false} onChange={(v) => set({ [k]: v } as Partial<QuoteDesign>)} label={t(label)} />
        ))}
      </div>
      <ErrorBox error={error} />
      <div className="gx-form-actions">{saved && <span className="muted small">{t("Saved.")}</span>}<button className="btn btn-primary" disabled={busy}>{t("Save")}</button></div>
    </form>
  );
}

export default function Services() {
  const { t, lang } = useI18n();
  const { user } = useAuth();
  const [list, setList] = useState<Service[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [words, setWords] = useState("");
  const [building, setBuilding] = useState(false);
  const [buildError, setBuildError] = useState<string | null>(null);
  const load = () => get<Service[]>("/api/services").then((x) => { setList(x); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, []);

  const build = async (e: FormEvent) => {
    e.preventDefault();
    setBuilding(true);
    setBuildError(null);
    try {
      const d = await post<Draft>("/api/services/ai-draft", { text: words });
      setDraft(toDraft({ ...empty(), ...d }));
      setOpen("new");
    } catch (err) {
      setBuildError((err as Error).message);
    } finally {
      setBuilding(false);
    }
  };
  const remove = async (id: number) => {
    try { await api("DELETE", `/api/services/${id}`); setOpen(null); load(); } catch (err) { setError((err as Error).message); }
  };
  const done = () => { setOpen(null); setDraft(null); setWords(""); load(); };

  return (
    <div className="narrow gx-narrow">
      <PageTitle kicker={t("Agency workspace")} title={t("Services")}
        subtitle={t("What your company offers. For each service, the AI asks the client your questions, follows your rules and sends your team a request card.")} />

      <form className="gx-card" onSubmit={build}>
        <div className="gx-card-title"><Sparkle weight="fill" /> {t("Describe a service to the AI")}</div>
        <textarea rows={4} value={words} onChange={(e) => setWords(e.target.value)} minLength={10} maxLength={6000} dir="auto" required
          placeholder={t("e.g. We arrange Schengen visas. We need passport copy, travel dates, bank statement. Fee 45 OMR. Takes 15 working days, no refund after submitting.")} />
        <ErrorBox error={buildError} />
        <div className="gx-form-actions">
          <button type="button" className="btn btn-ghost" onClick={() => { setDraft(empty()); setOpen("new"); }}><Plus />{t("Add by hand")}</button>
          <button className="btn btn-primary" disabled={building}>{building ? t("The AI is writing…") : t("Build the service")}</button>
        </div>
      </form>

      {open === "new" && draft && (
        <>
          <p className="muted small">{t("Check the draft, then save it. Nothing is saved yet.")}</p>
          <Editor initial={draft} id={null} builtIn={false} onSaved={done} onCancel={() => { setOpen(null); setDraft(null); }} />
        </>
      )}

      <ErrorBox error={error} onRetry={load} />
      {!list ? (!error && <Loading height={200} />) : (
        <div className="gx-svc-cards">
          {list.map((s) => open === s.id ? (
            <Editor key={s.id} initial={toDraft(s)} id={s.id} builtIn={!!s.key} custom={s.workflow_custom} onSaved={done} onCancel={() => setOpen(null)} onDelete={() => remove(s.id)} />
          ) : (
            <button key={s.id} type="button" className={`gx-card gx-svc-card ${s.is_active ? "" : "off"}`} onClick={() => setOpen(s.id)}>
              <span className="gx-row-between">
                <strong>{lang === "ar" ? s.name_ar : s.name_en}</strong>
                <span className="muted small">{s.is_active ? t(PRICING_LABELS[s.pricing]) : t("Switched off")}</span>
              </span>
              {(lang === "ar" ? s.description_ar : s.description_en) && <span className="muted small">{lang === "ar" ? s.description_ar : s.description_en}</span>}
              <span className="muted small">
                {t("{n} questions", { n: s.fields.length })}
                {s.parts.length > 0 && <> · {s.parts.map((p) => t(PART_LABELS[p])).join(", ")}</>}
                {s.pricing === "fixed" && s.price != null && <> · {s.price}</>}
              </span>
            </button>
          ))}
        </div>
      )}

      <PaymentCard />
      {user?.role === "company_admin" && <SlaCard />}
      {user?.company?.addons?.includes("quotes") && <QuoteDesignCard />}
    </div>
  );
}
