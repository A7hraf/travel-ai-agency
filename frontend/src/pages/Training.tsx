import { FormEvent, useEffect, useState } from "react";
import { del, get, post, put } from "../api";
import { Empty, ErrorBox, Field, PageHeader } from "../components/ui";
import type { TrainingExample } from "../types";

export default function Training() {
  const [items, setItems] = useState<TrainingExample[] | null>(null);
  const [editing, setEditing] = useState<TrainingExample | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = () => get<TrainingExample[]>("/api/training").then(setItems).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  const reset = () => { setEditing(null); setQuestion(""); setAnswer(""); };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      if (editing) await put(`/api/training/${editing.id}`, { question, answer });
      else await post("/api/training", { question, answer });
      reset();
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const remove = async (item: TrainingExample) => {
    if (!confirm("Delete this answer?")) return;
    await del(`/api/training/${item.id}`);
    if (editing?.id === item.id) reset();
    load();
  };

  const shown = (items ?? []).filter((i) => `${i.question} ${i.answer}`.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="narrow">
      <PageHeader title="AI training"
        subtitle="Teach your AI consultant how your company answers. When a customer asks something similar, in Arabic or English, the AI answers your way." />

      <form className="card" onSubmit={save}>
        <h3>{editing ? "Edit answer" : "Teach a new answer"}</h3>
        <Field label="Customer question" hint="Write it the way customers ask, e.g. «هل تقبلون الدفع بالتقسيط؟» or “Do you offer installments?”">
          <input value={question} onChange={(e) => setQuestion(e.target.value)} required minLength={2} maxLength={1000} dir="auto" />
        </Field>
        <Field label="Your company's answer">
          <textarea rows={4} value={answer} onChange={(e) => setAnswer(e.target.value)} required maxLength={4000} dir="auto" />
        </Field>
        <ErrorBox error={error} />
        <div className="row-gap">
          <button className="btn btn-primary">{editing ? "Save" : "Add to training"}</button>
          {editing && <button type="button" className="btn btn-ghost" onClick={reset}>Cancel</button>}
        </div>
      </form>

      <div className="toolbar"><input placeholder="Search answers" value={filter} onChange={(e) => setFilter(e.target.value)} /></div>
      {items === null ? <div className="loading">Loading…</div> : shown.length === 0 ? (
        <Empty>No answers yet. Add the questions customers ask you most.</Empty>
      ) : (
        <div className="qa-list">
          {shown.map((item) => (
            <div key={item.id} className="qa">
              <div className="qa-q" dir="auto">{item.question}</div>
              <div className="qa-a" dir="auto">{item.answer}</div>
              <div className="qa-actions">
                <button className="btn btn-sm" onClick={() => { setEditing(item); setQuestion(item.question); setAnswer(item.answer); window.scrollTo(0, 0); }}>Edit</button>
                <button className="btn btn-sm btn-danger" onClick={() => remove(item)}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="muted small" style={{ marginTop: "1rem" }}>
        The AI also learns from your packages (titles, descriptions, tags) and the policies in “AI &amp; WhatsApp”.
        Each company's training is private: it is never used for another company.
      </p>
    </div>
  );
}
