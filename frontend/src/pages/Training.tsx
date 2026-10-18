import { FormEvent, useEffect, useState } from "react";
import { del, get, post, put } from "../api";
import { ConfirmSheet, PageTitle } from "../components/admin/AdminUI";
import { ChatsCircle, GraduationCap, MagnifyingGlass, PencilSimple, Plus, ShieldCheck, Trash } from "../components/Icon";
import { ErrorBox, Field } from "../components/ui";
import { useI18n } from "../lang";
import type { TrainingExample } from "../types";

export default function Training() {
  const { t } = useI18n();
  const [items, setItems] = useState<TrainingExample[] | null>(null);
  const [editing, setEditing] = useState<TrainingExample | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState<TrainingExample | null>(null);

  const load = () => get<TrainingExample[]>("/api/training").then(setItems).catch((e) => setListError(e.message));
  useEffect(() => { load(); }, []);

  const reset = () => { setEditing(null); setQuestion(""); setAnswer(""); };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      if (editing) await put(`/api/training/${editing.id}`, { question, answer });
      else await post("/api/training", { question, answer });
      setNotice(editing ? t("Answer saved. The AI uses it from the next customer message.") : t("Answer added. The AI uses it from the next customer message."));
      reset();
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (item: TrainingExample) => {
    setDeleting(null);
    setListError(null);
    setNotice(null);
    try {
      await del(`/api/training/${item.id}`);
      if (editing?.id === item.id) reset();
      load();
    } catch (err) {
      setListError((err as Error).message);
    }
  };

  const shown = (items ?? []).filter((i) => `${i.question} ${i.answer}`.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="narrow ad-narrow">
      <PageTitle kicker={t("Agency workspace")} title={t("AI training")}
        subtitle={t("Teach your AI consultant how your company answers. When a customer asks something similar, in Arabic or English, the AI answers your way.")} />

      <form className={`ad-card tr-form ${editing ? "editing" : ""}`} onSubmit={save}>
        <h2 className="ad-card-title"><span className="ad-card-icon"><GraduationCap /></span>{editing ? t("Edit answer") : t("Teach a new answer")}</h2>
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

      <div className="ad-toolbar tr-toolbar">
        <h2 className="tr-count">{items ? t("{n} answers", { n: items.length }) : t("Answers")}</h2>
        <div className="ad-search">
          <MagnifyingGlass aria-hidden="true" />
          <input type="search" placeholder={t("Search answers")} aria-label={t("Search answers")} value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
      </div>
      <ErrorBox error={listError} />
      {items === null ? (listError ? null : <div className="skeleton" style={{ height: 120, borderRadius: 20 }} />) : shown.length === 0 ? (
        <div className="empty">
          <ChatsCircle className="empty-icon" />
          <strong>{filter.trim() && items.length > 0 ? t("No results for this filter.") : t("No answers yet. Add the questions customers ask you most.")}</strong>
        </div>
      ) : (
        <ul className="qa-list">
          {shown.map((item) => (
            <li key={item.id} className={`qa ${editing?.id === item.id ? "editing" : ""}`}>
              <div className="qa-q"><span className="qa-tag" aria-hidden="true">{t("Q")}</span><span dir="auto">{item.question}</span></div>
              <div className="qa-a"><span className="qa-tag a" aria-hidden="true">{t("A")}</span><span dir="auto">{item.answer}</span></div>
              <div className="qa-actions">
                <button className="btn btn-sm btn-soft" onClick={() => { setEditing(item); setQuestion(item.question); setAnswer(item.answer); setNotice(null); window.scrollTo({ top: 0, behavior: "smooth" }); }}><PencilSimple />{t("Edit")}</button>
                <button className="btn btn-sm btn-danger" onClick={() => setDeleting(item)}><Trash />{t("Delete")}</button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="tr-foot">
        <ShieldCheck />
        <span>{t("The AI also learns from your packages (titles, descriptions, tags) and the policies in “AI & WhatsApp”.")}{" "}
        {t("Each company's training is private: it is never used for another company.")}</span>
      </p>
      {deleting && (
        <ConfirmSheet title={t("Delete this answer?")} text={<span dir="auto">{deleting.question}</span>} tone="danger"
          confirmLabel={t("Delete")} onConfirm={() => remove(deleting)} onCancel={() => setDeleting(null)} />
      )}
    </div>
  );
}
