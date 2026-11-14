import { FormEvent, useEffect, useRef, useState } from "react";
import { api, get, post } from "../api";
import { PageTitle } from "../components/admin/AdminUI";
import { Lightbulb, MagnifyingGlass, PaperPlaneRight, Sparkle, Trash } from "../components/Icon";
import Markdown from "../components/insights/Markdown";
import { ErrorBox, Loading } from "../components/ui";
import { useI18n } from "../lang";
import { dateTime } from "../util";

interface Msg { id: number; role: "user" | "assistant" | "note"; content: string; created_at: string }

const COMPANY_IDEAS = ["What should I do first today?", "Which services and suppliers earn me the most?",
  "How can I get more quotations approved?", "What do my customers ask for that I don't offer?"];
const PLATFORM_IDEAS = ["Which agencies need my help this week?", "Which features should I build or improve next?",
  "Are there errors or weak spots to fix in the system?", "Which agencies could upgrade their plan?"];

/** The AI advisor: a chat about the business (a company's own figures, or the platform's for the owner). */
export default function Advisor({ platform }: { platform?: boolean }) {
  const { t } = useI18n();
  const base = platform ? "/api/system/advisor" : "/api/advisor";
  const [msgs, setMsgs] = useState<Msg[] | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const load = () => get<Msg[]>(base).then((x) => { setMsgs(x); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, [base]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [msgs?.length, busy]);

  const send = async (q: string) => {
    if (!q.trim() || busy) return;
    setBusy(true); setError(null);
    setMsgs((m) => [...(m ?? []), { id: -1, role: "user", content: q, created_at: new Date().toISOString() }]);
    setText("");
    try {
      const got = await post<Msg[]>(base, { text: q });
      setMsgs((m) => [...(m ?? []).filter((x) => x.id !== -1), ...got]);
    } catch (e) { setError((e as Error).message); load(); } finally { setBusy(false); }
  };
  const submit = (e: FormEvent) => { e.preventDefault(); send(text); };
  const ideas = platform ? PLATFORM_IDEAS : COMPANY_IDEAS;

  return (
    <div className="narrow gx-narrow">
      <PageTitle kicker={platform ? t("Platform") : t("Agency workspace")} title={t("AI advisor")}
        subtitle={platform ? t("Ask about your agencies, the platform's figures, errors and what to build next. The advisor also raises findings by itself every day.")
          : t("Ask about your business: it answers from your own figures (requests, quotations, suppliers, team). It also raises findings by itself every day.")}
        actions={<span className="gx-adv-actions">
          {platform && <button type="button" className="btn btn-soft" disabled={busy}
            onClick={() => post<Msg[]>(`${base}/check`).then(setMsgs).catch((e) => setError((e as Error).message))}><MagnifyingGlass />{t("Look for findings now")}</button>}
          {msgs && msgs.length > 0 && <button type="button" className="btn btn-ghost" onClick={() => api("DELETE", base).then(() => setMsgs([])).catch(() => {})}><Trash />{t("Clear")}</button>}
        </span>} />
      <ErrorBox error={error} onRetry={load} />
      {!msgs ? (!error && <Loading height={240} />) : (
        <div className="gx-adv">
          {msgs.length === 0 && <p className="muted">{t("Ask your first question, or pick one below.")}</p>}
          {msgs.map((m) => (
            <div key={m.id + m.created_at} className={`gx-adv-msg ${m.role}`}>
              {m.role === "note" && <div className="gx-adv-note-head"><Lightbulb weight="fill" />{t("The advisor noticed")}</div>}
              {m.role === "user" ? <div dir="auto">{m.content}</div> : <Markdown text={m.content} />}
              <div className="gx-adv-time">{dateTime(m.created_at)}</div>
            </div>
          ))}
          {busy && <div className="gx-adv-msg assistant"><span className="muted"><Sparkle weight="fill" /> {t("Reading your figures…")}</span></div>}
          <div ref={end} />
        </div>
      )}
      <div className="gx-chips gx-adv-ideas">
        {ideas.map((q) => <button key={q} type="button" className="gx-chip" disabled={busy} onClick={() => send(t(q))}>{t(q)}</button>)}
      </div>
      <form className="gx-adv-form" onSubmit={submit}>
        <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} maxLength={4000} dir="auto" placeholder={t("Ask the advisor…")}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }} aria-label={t("Ask the advisor…")} />
        <button className="btn btn-primary" disabled={busy || text.trim().length < 2} aria-label={t("Send")}><PaperPlaneRight className="flip" /></button>
      </form>
    </div>
  );
}
