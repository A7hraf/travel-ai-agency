import { FormEvent, useEffect, useState } from "react";
import { del, get, post, put } from "../api";
import { Empty, ErrorBox, Field, PageHeader } from "../components/ui";
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
    if (!confirm(t("Delete this answer?"))) return;
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
    <div className="narrow">
      <PageHeader title={t("AI training")}
        subtitle={t("Teach your AI consultant how your company answers. When a customer asks something similar, in Arabic or English, the AI answers your way.")} />

      <form className="card" onSubmit={save}>
        <h3>{editing ? t("Edit answer") : t("Teach a new answer")}</h3>
        <Field label={t("Customer question")} hint={t("Write it the way customers ask, e.g. {ar} or {en}", { ar: "«هل تقبلون الدفع بالتقسيط؟»", en: "“Do you offer installments?”" })}>
          <input value={question} onChange={(e) => setQuestion(e.target.value)} required minLength={2} maxLength={1000} dir="auto" />
        </Field>
        <Field label={t("Your company's answer")}>
          <textarea rows={4} value={answer} onChange={(e) => setAnswer(e.target.value)} required maxLength={4000} dir="auto" />
        </Field>
        <ErrorBox error={error} />
        {notice && <div className="ok-box" role="status">{notice}</div>}
        <div className="row-gap">
          <button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : editing ? t("Save") : t("Add to training")}</button>
          {editing && <button type="button" className="btn btn-ghost" onClick={reset}>{t("Cancel")}</button>}
        </div>
      </form>

      <div className="toolbar"><input placeholder={t("Search answers")} aria-label={t("Search answers")} value={filter} onChange={(e) => setFilter(e.target.value)} /></div>
      <ErrorBox error={listError} />
      {items === null ? <div className="loading">{listError ? "" : t("Loading…")}</div> : shown.length === 0 ? (
        <Empty>{filter.trim() && items.length > 0 ? t("No results for this filter.") : t("No answers yet. Add the questions customers ask you most.")}</Empty>
      ) : (
        <div className="qa-list">
          {shown.map((item) => (
            <div key={item.id} className="qa">
              <div className="qa-q" dir="auto">{item.question}</div>
              <div className="qa-a" dir="auto">{item.answer}</div>
              <div className="qa-actions">
                <button className="btn btn-sm" onClick={() => { setEditing(item); setQuestion(item.question); setAnswer(item.answer); setNotice(null); window.scrollTo(0, 0); }}>{t("Edit")}</button>
                <button className="btn btn-sm btn-danger" onClick={() => remove(item)}>{t("Delete")}</button>
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="muted small" style={{ marginTop: "1rem" }}>
        {t("The AI also learns from your packages (titles, descriptions, tags) and the policies in “AI & WhatsApp”.")}{" "}
        {t("Each company's training is private: it is never used for another company.")}
      </p>
    </div>
  );
}
