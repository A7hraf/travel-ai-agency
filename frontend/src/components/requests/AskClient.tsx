import { FormEvent, useState } from "react";
import { post } from "../../api";
import { useAuth } from "../../auth";
import { useI18n } from "../../lang";
import type { Ticket, TicketQuestion } from "../../types";
import { dateTime } from "../../util";
import { ChatCircleDots, CheckCircle, Hourglass } from "../Icon";
import { ErrorBox } from "../ui";

const KINDS: { key: TicketQuestion["kind"]; label: string; hint: string }[] = [
  { key: "info", label: "Information", hint: "What should the AI ask? For example: which area of Dubai, the children's ages…" },
  { key: "documents", label: "Documents", hint: "The missing documents are listed for the client. Add anything else here." },
  { key: "meeting", label: "A meeting or call", hint: "The client is asked which times suit them and which don't." },
  { key: "feedback", label: "Why the choices didn't suit", hint: "The client is asked what they'd like instead and why." },
];

/** The team asks the client through the AI (in the client's chat and language); the answers come back here. */
export default function AskClient({ ticket, onChange }: { ticket: Ticket; onChange: (t: Ticket) => void }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const [kind, setKind] = useState<TicketQuestion["kind"]>("info");
  const [note, setNote] = useState("");
  const [answering, setAnswering] = useState<number | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const closed = ticket.stage === "closed";
  const questions = ticket.questions ?? [];
  const run = async (fn: () => Promise<Ticket>) => {
    setBusy(true); setError(null);
    try { onChange(await fn()); return true; } catch (e) { setError((e as Error).message); return false; } finally { setBusy(false); }
  };
  const ask = async (e: FormEvent) => {
    e.preventDefault();
    if (await run(() => post<Ticket>(`/api/tickets/${ticket.id}/ask`, { kind, note }))) setNote("");
  };
  const record = async (e: FormEvent) => {
    e.preventDefault();
    if (answering && await run(() => post<Ticket>(`/api/tickets/${ticket.id}/questions/${answering}/answer`, { answer }))) {
      setAnswering(null); setAnswer("");
    }
  };
  const info = KINDS.find((k) => k.key === kind)!;

  return (
    <section className="rw-card gx-ask">
      <h3><ChatCircleDots /> {t("Ask the client")}</h3>
      <p className="muted small">{t("The AI writes to the client in their chat and language, then brings the answer back here.")}</p>
      {questions.length > 0 && (
        <ul className="gx-ask-list">
          {questions.map((q) => (
            <li key={q.id} className={q.answered_at ? "done" : "open"}>
              {q.answered_at ? <CheckCircle weight="fill" /> : <Hourglass weight="fill" />}
              <div>
                <strong>{t(KINDS.find((k) => k.key === q.kind)?.label ?? q.kind)}</strong>{q.note && <span dir="auto"> · {q.note}</span>}
                <small className="muted"><bdi>{q.by}</bdi> · {dateTime(q.at)}</small>
                {q.answered_at ? (
                  <p className="gx-ask-answer" dir="auto">“{q.answer}” <small className="muted">· {dateTime(q.answered_at)}</small></p>
                ) : can("tickets.manage") && !closed && (answering === q.id ? (
                  <form onSubmit={record} className="gx-ask-row">
                    <input dir="auto" maxLength={2000} required value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder={t("The client's answer")} />
                    <button className="btn btn-sm btn-primary" disabled={busy}>{t("Save")}</button>
                  </form>
                ) : (
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setAnswering(q.id); setAnswer(""); }}>{t("Answered by phone? Write it")}</button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
      {can("tickets.manage") && !closed && (
        <form onSubmit={ask} className="gx-ask-form">
          <div className="gx-ask-kinds" role="radiogroup" aria-label={t("What do you need?")}>
            {KINDS.map((k) => (
              <button key={k.key} type="button" role="radio" aria-checked={kind === k.key} className={`chip-btn ${kind === k.key ? "active" : ""}`} onClick={() => setKind(k.key)}>{t(k.label)}</button>
            ))}
          </div>
          <textarea rows={2} dir="auto" maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t(info.hint)}
            required={kind === "info"} minLength={kind === "info" ? 3 : undefined} aria-label={t("What do you need?")} />
          <button className="btn btn-sm btn-primary" disabled={busy || (kind === "info" && note.trim().length < 3)}>{t("Ask through the AI")}</button>
        </form>
      )}
      <ErrorBox error={error} />
    </section>
  );
}
