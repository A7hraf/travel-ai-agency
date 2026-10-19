import { FormEvent, KeyboardEvent, ReactNode, useEffect, useRef, useState } from "react";
import { del, get, patch, post, put } from "../../api";
import { trServer, useI18n } from "../../lang";
import type { AIKnowledge, TrainingExample, TrainingImportResult, TryAIResult } from "../../types";
import { ConfirmSheet } from "../admin/AdminUI";
import {
  Books, ChatsCircle, CheckCircle, GraduationCap, Lightning, MagnifyingGlass, PaperPlaneRight, PencilSimple,
  Plus, Robot, ShieldCheck, Sparkle, Trash, UploadSimple, User as UserIcon,
} from "../Icon";
import { moneyText } from "../Money";
import { ChatText, ErrorBox, Field } from "../ui";
import "./ai.css";
import "./i18n";

export type TrainingTab = "answers" | "knowledge" | "try";

/** Everything the AI learns from, in one place: trained answers, company knowledge and a test chat.
 *  `base` is /api/training for the company itself, or /api/system/companies/{id}/training for the owner. */
export default function TrainingWorkspace({ base, tab, onTab, settingsLink }: {
  base: string;
  tab: TrainingTab;
  onTab: (tab: TrainingTab) => void;
  /** Shown in the knowledge tab, e.g. a link to the storefront or settings. */
  settingsLink?: ReactNode;
}) {
  const { t } = useI18n();
  const [items, setItems] = useState<TrainingExample[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [knowledge, setKnowledge] = useState<AIKnowledge | null>(null);

  const load = () => get<TrainingExample[]>(base).then((x) => { setItems(x); setListError(null); }).catch((e) => setListError(e.message));
  const loadKnowledge = () => get<AIKnowledge>(`${base}/knowledge`).then(setKnowledge).catch(() => {});
  useEffect(() => { setItems(null); load(); loadKnowledge(); }, [base]);

  const tabs: [TrainingTab, string, ReactNode][] = [
    ["answers", t("Answers"), items ? <span className="ai-tab-count">{items.length}</span> : null],
    ["knowledge", t("Company knowledge"), null],
    ["try", t("Try your AI"), null],
  ];
  const nothingYet = items !== null && items.length === 0 && knowledge !== null && !knowledge.knowledge_base.trim();

  return (
    <div className="ai-workspace">
      <div className="cd-tabs ai-tabs" role="tablist" aria-label={t("AI training")}>
        {tabs.map(([key, label, extra]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "active" : ""} onClick={() => onTab(key)}>
            {key === "try" && <Sparkle weight="fill" aria-hidden="true" />}{label}{extra}
          </button>
        ))}
      </div>

      {nothingYet && tab !== "try" && <HowItWorks onTab={onTab} />}

      {tab === "answers" && <AnswersTab base={base} items={items} listError={listError} reload={load} />}
      {tab === "knowledge" && <KnowledgeTab base={base} knowledge={knowledge} onSaved={setKnowledge} extra={settingsLink} />}
      {tab === "try" && <TryTab base={base} onTaught={load} agent={knowledge?.ai_agent_name ?? "AI"} />}

      <p className="tr-foot">
        <ShieldCheck />
        <span>{t("Each company's training is private: it is never used for another company.")}</span>
      </p>
    </div>
  );
}

function HowItWorks({ onTab }: { onTab: (tab: TrainingTab) => void }) {
  const { t } = useI18n();
  return (
    <section className="ad-card">
      <h2 className="ad-card-title"><span className="ad-card-icon"><GraduationCap /></span>{t("How AI training works")}</h2>
      <p className="ad-card-note">{t("Your AI consultant already knows your packages (titles, prices, dates, descriptions). Training teaches it everything else about your company, in plain words. No technical skills needed.")}</p>
      <ol className="ai-how">
        <li><span className="ai-how-num">1</span><div>
          <strong>{t("Teach answers")}</strong>
          <p>{t("Write the questions customers ask you and your company's answer. When a customer asks something similar, in Arabic or English, the AI answers your way.")}</p>
          <button className="btn btn-sm btn-soft" onClick={() => onTab("answers")}>{t("Add an answer")}</button>
        </div></li>
        <li><span className="ai-how-num">2</span><div>
          <strong>{t("Add company knowledge")}</strong>
          <p>{t("Paste your policies: payment, deposit, cancellation, visas, office hours. The AI uses them and never contradicts them.")}</p>
          <button className="btn btn-sm btn-soft" onClick={() => onTab("knowledge")}>{t("Add knowledge")}</button>
        </div></li>
        <li><span className="ai-how-num">3</span><div>
          <strong>{t("Try your AI")}</strong>
          <p>{t("Ask a question as if you were a customer and see the real answer. If it's not right, correct it and teach it in one click.")}</p>
          <button className="btn btn-sm btn-soft" onClick={() => onTab("try")}>{t("Try your AI")}</button>
        </div></li>
      </ol>
    </section>
  );
}

// --- Answers ------------------------------------------------------------------------------

function AnswersTab({ base, items, listError, reload }: {
  base: string; items: TrainingExample[] | null; listError: string | null; reload: () => void;
}) {
  const { t } = useI18n();
  const [editing, setEditing] = useState<TrainingExample | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState<TrainingExample | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);

  const reset = () => { setEditing(null); setQuestion(""); setAnswer(""); };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      if (editing) await put(`${base}/${editing.id}`, { question, answer });
      else await post(base, { question, answer });
      setNotice(editing ? t("Answer saved. The AI uses it from the next customer message.") : t("Answer added. The AI uses it from the next customer message."));
      reset();
      reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (item: TrainingExample) => {
    setDeleting(null);
    setRowError(null);
    setNotice(null);
    try {
      await del(`${base}/${item.id}`);
      if (editing?.id === item.id) reset();
      reload();
    } catch (err) {
      setRowError((err as Error).message);
    }
  };

  const needle = filter.trim().toLowerCase();
  const shown = (items ?? []).filter((i) => `${i.question} ${i.answer}`.toLowerCase().includes(needle));

  return (
    <>
      <form ref={formRef} className={`ad-card tr-form ${editing ? "editing" : ""}`} onSubmit={save}>
        <h2 className="ad-card-title"><span className="ad-card-icon"><GraduationCap /></span>{editing ? t("Edit answer") : t("Teach a new answer")}
          <span className="spacer" />
          {!editing && <button type="button" className="btn btn-sm btn-ghost" aria-expanded={importOpen} onClick={() => setImportOpen((o) => !o)}><UploadSimple />{t("Import many answers")}</button>}
        </h2>
        <Field label={t("Customer question")} hint={t("Write it the way customers ask, e.g. {ar} or {en}", { ar: "«هل تقبلون الدفع بالتقسيط؟»", en: "“Do you offer installments?”" })}>
          <input value={question} onChange={(e) => setQuestion(e.target.value)} required minLength={2} maxLength={1000} dir="auto" />
        </Field>
        <Field label={t("Your company's answer")}>
          <textarea rows={4} value={answer} onChange={(e) => setAnswer(e.target.value)} required maxLength={4000} dir="auto" />
        </Field>
        <ErrorBox error={error} />
        {notice && <div className="ok-box ad-notice" role="status">{notice}</div>}
        <div className="ad-form-actions">
          <button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : editing ? t("Save") : <><Plus weight="bold" />{t("Add to training")}</>}</button>
          {editing && <button type="button" className="btn btn-ghost" onClick={reset}>{t("Cancel")}</button>}
        </div>
      </form>

      {importOpen && <ImportCard base={base} onDone={() => { reload(); }} onClose={() => setImportOpen(false)} />}

      <div className="ad-toolbar tr-toolbar">
        <h2 className="tr-count">{items ? t("{n} answers", { n: items.length }) : t("Answers")}</h2>
        <div className="ad-search">
          <MagnifyingGlass aria-hidden="true" />
          <input type="search" placeholder={t("Search answers")} aria-label={t("Search answers")} value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
      </div>
      <ErrorBox error={listError ?? rowError} />
      {items === null ? (listError ? null : <div className="skeleton" style={{ height: 120, borderRadius: 20 }} />) : shown.length === 0 ? (
        <div className="empty">
          <ChatsCircle className="empty-icon" />
          <strong>{needle && items.length > 0 ? t("No results for this filter.") : t("No answers yet. Add the questions customers ask you most.")}</strong>
          {!needle && <span>{t("Tip: start with 5 to 10 questions, such as payment, deposit, visas and what's included.")}</span>}
        </div>
      ) : (
        <ul className="qa-list">
          {shown.map((item) => (
            <li key={item.id} className={`qa ${editing?.id === item.id ? "editing" : ""}`}>
              <div className="qa-q"><span className="qa-tag" aria-hidden="true">{t("Q")}</span><span dir="auto">{item.question}</span></div>
              <div className="qa-a"><span className="qa-tag a" aria-hidden="true">{t("A")}</span><span dir="auto">{item.answer}</span></div>
              <div className="qa-actions">
                <button className="btn btn-sm btn-soft" onClick={() => {
                  setEditing(item); setQuestion(item.question); setAnswer(item.answer); setNotice(null);
                  formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                }}><PencilSimple />{t("Edit")}</button>
                <button className="btn btn-sm btn-danger" onClick={() => setDeleting(item)}><Trash />{t("Delete")}</button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {deleting && (
        <ConfirmSheet title={t("Delete this answer?")} text={<span dir="auto">{deleting.question}</span>} tone="danger"
          confirmLabel={t("Delete")} onConfirm={() => remove(deleting)} onCancel={() => setDeleting(null)} />
      )}
    </>
  );
}

const IMPORT_EXAMPLE = "Do you offer installments? | Yes, you can pay in 3 monthly payments.\nهل التأشيرة مشمولة؟ | لا، التأشيرة غير مشمولة ونساعدك في إجراءاتها.";

function ImportCard({ base, onDone, onClose }: { base: string; onDone: () => void; onClose: () => void }) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<TrainingImportResult | null>(null);
  const [done, setDone] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (save: boolean) => {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const r = await post<TrainingImportResult>(`${base}/import`, { text, preview: !save });
      if (save) { setDone(r.added); setPreview(null); setText(""); onDone(); }
      else setPreview(r);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="ad-card ai-import">
      <h2 className="ad-card-title"><span className="ad-card-icon"><UploadSimple /></span>{t("Import many answers")}</h2>
      <p className="ad-card-note">{t("Paste one answer per line: the question, a | sign, then the answer. You can also paste two columns copied from Excel or Google Sheets, or a CSV file's text. Up to 200 at a time.")}</p>
      <Field label={t("Questions and answers")} hint={<>{t("Example:")} <code dir="auto" style={{ whiteSpace: "pre-wrap" }}>{IMPORT_EXAMPLE}</code></>}>
        <textarea rows={7} value={text} dir="auto" maxLength={200000} onChange={(e) => { setText(e.target.value); setPreview(null); setDone(null); }}
          placeholder={"question | answer"} />
      </Field>
      <ErrorBox error={error} />
      {done !== null && <div className="ok-box ad-notice" role="status">{t("{n} answers added to the training.", { n: done })}</div>}
      {preview && (
        <div aria-live="polite">
          <div className="ai-import-sum">
            <span className="ad-status on">{t("{n} new answers", { n: preview.rows.length })}</span>
            {preview.duplicates.length > 0 && <span className="ad-status off">{t("{n} already trained (skipped)", { n: preview.duplicates.length })}</span>}
            {preview.problems.length > 0 && <span className="ad-status warn">{t("{n} lines with a problem (skipped)", { n: preview.problems.length })}</span>}
          </div>
          <ul className="ai-import-list">
            {preview.problems.map((p) => <li key={`p${p.line}`} className="bad"><span className="ln">{t("Line {n}", { n: p.line })}</span>{trServer(p.error)}</li>)}
            {preview.rows.slice(0, 50).map((r) => (
              <li key={r.line}><span className="ln">{t("Line {n}", { n: r.line })}</span><strong dir="auto">{r.question}</strong> — <span dir="auto">{r.answer}</span></li>
            ))}
          </ul>
        </div>
      )}
      <div className="ad-form-actions">
        {preview && preview.rows.length > 0
          ? <button className="btn btn-primary" disabled={busy} onClick={() => run(true)}>{busy ? t("Saving…") : t("Import {n} answers", { n: preview.rows.length })}</button>
          : <button className="btn btn-primary" disabled={busy || !text.trim()} onClick={() => run(false)}>{busy ? t("Checking…") : t("Check the lines")}</button>}
        <button className="btn btn-ghost" onClick={onClose}>{t("Close")}</button>
      </div>
    </section>
  );
}

// --- Company knowledge ----------------------------------------------------------------------

function KnowledgeTab({ base, knowledge, onSaved, extra }: {
  base: string; knowledge: AIKnowledge | null; onSaved: (k: AIKnowledge) => void; extra?: ReactNode;
}) {
  const { t } = useI18n();
  const [k, setK] = useState<AIKnowledge | null>(knowledge);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (knowledge && !k) setK(knowledge); }, [knowledge]);
  if (!k) return <div className="skeleton" style={{ height: 320, borderRadius: 24 }} />;

  const set = <K extends keyof AIKnowledge>(key: K, v: AIKnowledge[K]) => { setSaved(false); setK({ ...k, [key]: v }); };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await patch<AIKnowledge>(`${base}/knowledge`, {
        ai_agent_name: k.ai_agent_name, ai_welcome_message: k.ai_welcome_message ?? "",
        ai_welcome_message_ar: k.ai_welcome_message_ar ?? "", ai_instructions: k.ai_instructions, knowledge_base: k.knowledge_base,
      });
      setK(updated);
      onSaved(updated);
      setSaved(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="ad-card" onSubmit={save}>
      <h2 className="ad-card-title"><span className="ad-card-icon"><Books /></span>{t("Company knowledge")}</h2>
      <p className="ad-card-note">{t("What the AI should know about your company and how it should behave. It applies to the website chat and WhatsApp.")}</p>
      <Field label={t("Knowledge & policies")} hint={t("Payment methods, deposit, cancellation, visas, office hours… The AI uses this to answer and never contradicts it. Arabic or English.")}>
        <textarea rows={10} maxLength={30000} dir="auto" value={k.knowledge_base} onChange={(e) => set("knowledge_base", e.target.value)}
          placeholder={t("e.g. We take a 20% deposit to book. Cancellation is free up to 30 days before departure. Office hours: Sat–Thu 9am–6pm.")} />
      </Field>
      <h3 className="co-form-h">{t("Personality")}</h3>
      <div className="ad-grid-2">
        <Field label={t("Agent name")} hint={t("How the AI introduces itself to customers.")}>
          <input value={k.ai_agent_name} onChange={(e) => set("ai_agent_name", e.target.value)} required maxLength={80} dir="auto" />
        </Field>
        <div />
        <Field label={t("Welcome message (English)")} hint={t("Empty = default greeting.")}>
          <textarea rows={2} maxLength={1000} dir="auto" value={k.ai_welcome_message ?? ""} onChange={(e) => set("ai_welcome_message", e.target.value)} />
        </Field>
        <Field label="رسالة الترحيب (عربي)" hint={t("Empty = default Arabic greeting.")}>
          <textarea rows={2} maxLength={1000} dir="rtl" value={k.ai_welcome_message_ar ?? ""} onChange={(e) => set("ai_welcome_message_ar", e.target.value)} />
        </Field>
      </div>
      <Field label={t("Extra instructions")} hint={t("Style and selling rules, e.g. \"Always suggest travel insurance\". For question-and-answer teaching use AI training.")}>
        <textarea rows={4} maxLength={8000} dir="auto" value={k.ai_instructions} onChange={(e) => set("ai_instructions", e.target.value)} />
      </Field>
      <ErrorBox error={error} />
      {saved && <div className="ok-box ad-notice" role="status">{t("AI settings saved. They apply to the next customer message.")}</div>}
      <div className="ad-form-actions">
        <button className="btn btn-primary" disabled={busy} aria-busy={busy}>{busy ? t("Saving…") : t("Save knowledge")}</button>
        {extra}
      </div>
    </form>
  );
}

// --- Try your AI ------------------------------------------------------------------------------

interface Turn { role: "user" | "assistant"; content: string; result?: TryAIResult; question?: string; failed?: boolean }

const SUGGESTIONS = ["Do you have a honeymoon trip in December?", "ابغى رحلة عائلية لتركيا", "Do you offer installments?"];

function TryTab({ base, onTaught, agent }: { base: string; onTaught: () => void; agent: string }) {
  const { t, lang } = useI18n();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [teaching, setTeaching] = useState<number | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [turns.length, busy]);

  const send = async (message: string) => {
    const msg = message.trim();
    if (!msg || busy) return;
    const history = turns.filter((x) => !x.failed).map(({ role, content }) => ({ role, content }));
    setTurns((prev) => [...prev, { role: "user", content: msg }]);
    setText("");
    setBusy(true);
    try {
      const r = await post<TryAIResult>(`${base}/try`, { message: msg, history });
      setTurns((prev) => [...prev, r.ok && r.reply
        ? { role: "assistant", content: r.reply, result: r, question: msg }
        : { role: "assistant", content: trServer(r.error) || t("The AI could not answer."), result: r, question: msg, failed: true }]);
    } catch (err) {
      setTurns((prev) => [...prev, { role: "assistant", content: (err as Error).message, question: msg, failed: true }]);
    } finally {
      setBusy(false);
    }
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(text); }
  };

  return (
    <section className="ad-card ai-try">
      <div className="ai-try-head">
        <h2 className="ad-card-title" style={{ margin: 0 }}><span className="ad-card-icon"><Sparkle weight="fill" /></span>{t("Try your AI")}</h2>
        <span className="ad-status cyan">{t("Test mode")}</span>
        <span className="spacer" />
        {turns.length > 0 && <button className="btn btn-sm btn-ghost" onClick={() => { setTurns([]); setTeaching(null); }}>{t("New test chat")}</button>}
      </div>
      <p className="ad-card-note">{t("Type a question as if you were a customer, in Arabic or English. You get the real answer with your packages, knowledge and trained answers. Nothing is saved: no chat, customer or booking is created.")}</p>

      <div className="ai-try-log" aria-live="polite">
        {turns.length === 0 && (
          <div className="ai-try-empty">
            <Robot aria-hidden="true" />
            <strong>{t("Ask your AI anything a customer would ask")}</strong>
            <div className="ai-suggest">{SUGGESTIONS.map((s) => <button key={s} className="btn btn-sm btn-soft" dir="auto" onClick={() => send(s)}>{s}</button>)}</div>
          </div>
        )}
        {turns.map((turn, i) => turn.role === "user" ? (
          <div key={i} className="ai-turn user">
            <span className="ai-who"><UserIcon aria-hidden="true" />{t("You (as a customer)")}</span>
            <div className="ai-bubble" dir="auto">{turn.content}</div>
          </div>
        ) : (
          <div key={i} className={`ai-turn ai ${turn.failed ? "bad" : ""}`}>
            <span className="ai-who"><Robot aria-hidden="true" />{agent}</span>
            <div className="ai-bubble" dir="auto"><ChatText text={turn.content} /></div>
            {turn.result && <ReplyDetails result={turn.result} lang={lang} />}
            {!turn.failed && teaching !== i && (
              <button className="btn btn-sm btn-soft" onClick={() => setTeaching(i)}><GraduationCap />{t("Teach this answer")}</button>
            )}
            {teaching === i && (
              <TeachForm base={base} question={turn.question ?? ""} answer={turn.content}
                onClose={() => setTeaching(null)} onSaved={onTaught} />
            )}
          </div>
        ))}
        {busy && <div className="ai-turn ai"><span className="ai-who"><Robot aria-hidden="true" />{agent}</span>
          <div className="ai-bubble"><span className="login-spin" aria-hidden="true" /> {t("Thinking…")}</div></div>}
        <div ref={endRef} />
      </div>

      <form className="ai-try-form" onSubmit={(e) => { e.preventDefault(); send(text); }}>
        <textarea rows={1} value={text} maxLength={2000} dir="auto" onChange={(e) => setText(e.target.value)} onKeyDown={onKey}
          placeholder={t("Write a customer question…")} aria-label={t("Write a customer question…")} />
        <button className="btn btn-primary" disabled={busy || !text.trim()}><PaperPlaneRight weight="fill" className="flip" />{t("Send")}</button>
      </form>
    </section>
  );
}

function ReplyDetails({ result, lang }: { result: TryAIResult; lang: "en" | "ar" }) {
  const { t } = useI18n();
  const sim = result.simulated;
  if (!result.used_answers.length && !result.packages.length && !sim.length) {
    return <div className="ai-meta"><span>{t("No trained answer matched this question.")}</span></div>;
  }
  return (
    <div className="ai-meta">
      {result.used_answers.length > 0 && (
        <div className="ai-meta-row"><span>{t("Trained answers used:")}</span>
          {result.used_answers.map((a) => <span key={a.id} className="ai-chip brand" dir="auto" title={a.answer}><CheckCircle weight="fill" />{a.question}</span>)}
        </div>
      )}
      {result.packages.length > 0 && (
        <div className="ai-meta-row"><span>{t("Packages it looked at:")}</span>
          {result.packages.map((p) => (
            <span key={p.id} className="ai-chip" dir="auto">{p.title}
              {p.price_per_person != null && p.currency ? ` · ${moneyText(p.price_per_person, p.currency, lang)}` : ""}</span>
          ))}
        </div>
      )}
      {sim.includes("booking") && <div className="ai-sim">{t("Test mode: in a real chat a booking ticket would be created here for your team. Nothing was booked and no seats were held.")}</div>}
      {sim.includes("handover") && <div className="ai-sim">{t("Test mode: in a real chat the customer would be handed to your team here.")}</div>}
    </div>
  );
}

function TeachForm({ base, question: q0, answer: a0, onClose, onSaved }: {
  base: string; question: string; answer: string; onClose: () => void; onSaved: () => void;
}) {
  const { t } = useI18n();
  const [question, setQuestion] = useState(q0);
  const [answer, setAnswer] = useState(a0);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post(base, { question, answer });
      setDone(true);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  if (done) {
    return <div className="ok-box ad-notice" role="status"><Lightning weight="fill" /> {t("Taught! Ask the question again to see the new answer.")}</div>;
  }
  return (
    <form className="ai-teach" onSubmit={save}>
      <p className="ad-card-note" style={{ marginTop: 0 }}>{t("Correct the answer if needed. The AI will answer this way when a customer asks something similar.")}</p>
      <Field label={t("Customer question")}>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} required minLength={2} maxLength={1000} dir="auto" />
      </Field>
      <Field label={t("Correct answer")}>
        <textarea rows={4} value={answer} onChange={(e) => setAnswer(e.target.value)} required maxLength={4000} dir="auto" />
      </Field>
      <ErrorBox error={error} />
      <div className="ad-form-actions">
        <button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : <><GraduationCap />{t("Save to training")}</>}</button>
        <button type="button" className="btn btn-ghost" onClick={onClose}>{t("Cancel")}</button>
      </div>
    </form>
  );
}
