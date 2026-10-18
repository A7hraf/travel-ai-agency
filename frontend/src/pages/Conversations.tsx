import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError, get, post } from "../api";
import { useAuth } from "../auth";
import {
  ArrowLeft, Check, Checks, ClockCountdown, Coffee, Globe, HandGrabbing, Headset, MagnifyingGlass, PaperPlaneRight,
  Phone, Robot, Sparkle, Ticket, User, WarningCircle, WhatsappLogo, Wrench,
} from "../components/Icon";
import { ChatText, ErrorBox } from "../components/ui";
import { ConfirmRequest, ConfirmSheet } from "../components/staff/Sheet";
import { initials, useStaff } from "../components/staff/StaffContext";
import { currentLocale, trServer, tr, useI18n } from "../lang";
import type { ConversationDetail, ConversationSummary, Message } from "../types";
import { customerLabel, dateTime, shortDate, usePolling } from "../util";

type Filter = "human" | "ai" | "closed" | "all";
const FILTERS: { value: Filter; label: string; tone: string }[] = [
  { value: "human", label: "Needs a human", tone: "amber" },
  { value: "ai", label: "AI handling", tone: "teal" },
  { value: "closed", label: "Closed", tone: "" },
  { value: "all", label: "All", tone: "" },
];

/** WhatsApp lets a business answer freely only within 24 hours of the customer's last message. */
const WHATSAPP_WINDOW_MS = 24 * 60 * 60 * 1000;

const draftKey = (id: number) => `travel_reply_draft_${id}`;

function readDraft(id: number): string {
  try {
    return sessionStorage.getItem(draftKey(id)) ?? "";
  } catch {
    return "";
  }
}

function writeDraft(id: number, text: string) {
  try {
    if (text) sessionStorage.setItem(draftKey(id), text);
    else sessionStorage.removeItem(draftKey(id));
  } catch {
    /* storage unavailable */
  }
}

/** "2 min", "26 h", "Yesterday", then the date. */
function ago(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return tr("now");
  if (minutes < 60) return tr("{n} min", { n: minutes });
  const hours = Math.round(minutes / 60);
  if (hours < 36) return tr("{n} h", { n: hours });
  if (hours < 48) return tr("Yesterday");
  return shortDate(iso);
}

function firstName(full: string): string {
  return full.trim().split(/\s+/)[0] ?? full;
}

type Pill = { cls: string; label: string };

/** Needs a human (amber) / With you (cyan) / With {name} (grey) / AI handling (teal) / Closed. */
function usePill(myId: number | undefined) {
  const { t } = useI18n();
  return (c: ConversationSummary): Pill => {
    if (c.status === "human") {
      if (!c.assigned_to) return { cls: "st-needs", label: t("Needs a human") };
      if (c.assigned_to.id === myId) return { cls: "st-mine", label: t("With you") };
      return { cls: "st-colleague", label: t("With {name}", { name: firstName(c.assigned_to.full_name) }) };
    }
    if (c.status === "ai") return { cls: "st-ai", label: t("AI handling") };
    return { cls: "st-closed", label: t("Closed") };
  };
}

function Channel({ channel }: { channel: ConversationSummary["channel"] }) {
  const { t } = useI18n();
  return channel === "whatsapp" ? (
    <span className="cv-channel wa"><WhatsappLogo weight="fill" aria-hidden="true" />{t("WhatsApp")}</span>
  ) : (
    <span className="cv-channel web"><Globe aria-hidden="true" />{t("Web")}</span>
  );
}

export default function Conversations() {
  const { id } = useParams();
  const { t } = useI18n();
  const { user } = useAuth();
  const { agentName } = useStaff();
  const [params, setParams] = useSearchParams();
  const raw = params.get("status");
  const filter: Filter = raw === "ai" || raw === "closed" || raw === "all" ? raw : "human";
  const [search, setSearch] = useState("");
  const [all, setAll] = useState<ConversationSummary[] | null>(null);
  const pill = usePill(user?.id);

  usePolling(() => {
    const q = new URLSearchParams({ limit: "500" });
    if (search.trim()) q.set("q", search.trim());
    get<ConversationSummary[]>(`/api/conversations?${q}`).then(setAll).catch(() => {});
  }, 5000, [search]);

  const counts: Record<Filter, number> = {
    human: all?.filter((c) => c.status === "human").length ?? 0,
    ai: all?.filter((c) => c.status === "ai").length ?? 0,
    closed: all?.filter((c) => c.status === "closed").length ?? 0,
    all: all?.length ?? 0,
  };
  const list = all?.filter((c) => filter === "all" || c.status === filter) ?? null;
  const qs = filter === "human" ? "" : `?status=${filter}`;
  const agent = agentName || t("The AI agent");

  return (
    <div className={`inbox ${id ? "has-chat" : ""}`}>
      <section className="inbox-list" aria-label={t("Conversations")}>
        <h1 className="screen-title">{t("Conversations")}</h1>
        <div className="chips scroll inbox-chips" role="group" aria-label={t("Status")}>
          {FILTERS.map((f) => (
            <button key={f.value} type="button" className={`cv-chip ${filter === f.value ? "active" : ""}`}
              aria-pressed={filter === f.value} onClick={() => setParams(f.value === "human" ? {} : { status: f.value })}>
              {t(f.label)}
              <span className={`count ${f.tone}`}>{counts[f.value]}</span>
            </button>
          ))}
        </div>
        <label className="search-field">
          <MagnifyingGlass aria-hidden="true" />
          <input type="search" placeholder={t("Search name, phone, email")} aria-label={t("Search name, phone, email")}
            value={search} onChange={(e) => setSearch(e.target.value)} />
        </label>
        <div className="cv-rows">
          {list === null && [0, 1, 2].map((i) => <div key={i} className="skeleton cv-skel" />)}
          {list?.length === 0 && (
            <div className="empty">
              <Coffee className="empty-icon" aria-hidden="true" />
              {search.trim()
                ? t("No results for this filter.")
                : filter === "human"
                  ? t("Nobody is waiting. {agent} has it covered.", { agent })
                  : t("No conversations yet.")}
            </div>
          )}
          {list?.map((c) => {
            const p = pill(c);
            const needs = c.status === "human" && !c.assigned_to;
            const label = customerLabel(c.customer);
            const ini = initials(label);
            return (
              <Link key={c.id} to={`/app/conversations/${c.id}${qs}`}
                className={`cv-row ${needs ? "needs" : ""} ${String(c.id) === id ? "selected" : ""}`}
                aria-current={String(c.id) === id ? "page" : undefined}>
                <span className={`cv-avatar ${needs ? "pulse" : ""}`} aria-hidden="true">{ini || <User />}</span>
                <span className="cv-row-main">
                  <span className="cv-row-top">
                    <bdi className="cv-name">{label}</bdi>
                    <span className="cv-time">{ago(c.last_message_at)}</span>
                  </span>
                  <span className="cv-preview" dir="auto">{trServer(c.last_message_preview) || "…"}</span>
                  <span className="cv-tags">
                    <span className={`pill ${p.cls}`}>{p.label}</span>
                    <Channel channel={c.channel} />
                  </span>
                </span>
              </Link>
            );
          })}
        </div>
      </section>
      <section className="inbox-chat">
        {id ? (
          <ConversationView key={id} id={Number(id)} backTo={`/app/conversations${qs}`} />
        ) : (
          <div className="empty cv-pick">
            <Headset className="empty-icon" aria-hidden="true" />
            {t("Select a conversation to see the chat.")}
          </div>
        )}
      </section>
    </div>
  );
}

function ConversationView({ id, backTo }: { id: number; backTo: string }) {
  const { can, user } = useAuth();
  const { t } = useI18n();
  const { agentName, refreshCounts } = useStaff();
  const navigate = useNavigate();
  const pill = usePill(user?.id);
  const [conv, setConv] = useState<ConversationDetail | null>(null);
  const [showTools, setShowTools] = useState(false);
  // The reply draft survives a reload or a new login (per conversation, this browser tab only).
  const [text, setTextState] = useState(() => readDraft(id));
  const [error, setError] = useState<string | null>(null);
  const [replyError, setReplyError] = useState<string | null>(null);
  const [windowClosed, setWindowClosed] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [acting, setActing] = useState<string | null>(null);
  const [confirmReq, setConfirmReq] = useState<ConfirmRequest | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const lastCount = useRef(0);

  const setText = (value: string) => {
    setTextState(value);
    writeDraft(id, value);
  };

  const load = () =>
    get<ConversationDetail>(`/api/conversations/${id}`).then(setConv).catch((e) => {
      if (e.status === 404) navigate("/app/conversations");
    });
  usePolling(load, 4000, [id]);

  const visibleCount = conv ? conv.messages.filter((m) => showTools || m.kind === "text").length : 0;
  useEffect(() => {
    if (conv && visibleCount !== lastCount.current) {
      lastCount.current = visibleCount;
      const el = scroller.current;
      if (el) el.scrollTop = el.scrollHeight;
    }
  }, [conv, visibleCount]);

  if (!conv) {
    return (
      <div className="chat-screen">
        <div className="chat-loading">{[0, 1, 2].map((i) => <div key={i} className="skeleton cv-skel" />)}</div>
      </div>
    );
  }

  const agent = agentName || t("AI agent");
  const canReply = can("conversations.reply");
  const mine = conv.status === "human" && conv.assigned_to?.id === user?.id;
  const colleague = conv.status === "human" && conv.assigned_to && conv.assigned_to.id !== user?.id ? conv.assigned_to : null;
  const lastCustomer = [...conv.messages].reverse().find((m) => m.sender === "customer");
  const expired = conv.channel === "whatsapp" && (
    !!windowClosed || !lastCustomer || Date.now() - new Date(lastCustomer.created_at).getTime() > WHATSAPP_WINDOW_MS
  );
  const p = pill(conv);
  const c = conv.customer;

  const run = async (path: "takeover" | "release" | "close", force = false) => {
    if (acting) return;
    setError(null);
    setActing(path);
    try {
      try {
        setConv(await post<ConversationDetail>(`/api/conversations/${id}/${path}${force ? "?force=true" : ""}`));
        // The reply can carry the previous assignee; read the conversation again to show who has it now.
        await load();
        refreshCounts();
      } catch (e) {
        // Someone else took it a moment ago: ask before taking it from them.
        if (path === "takeover" && !force && e instanceof ApiError && e.status === 409) {
          setConfirmReq({
            title: t("{message}. Do you want to take it over anyway?", { message: e.message.replace(/\.$/, "") }),
            text: t("They will see that you took over."),
            okLabel: t("Take over"),
            onConfirm: () => run("takeover", true),
          });
        } else {
          throw e;
        }
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setActing(null);
    }
  };

  const takeOver = () => {
    if (colleague) {
      const name = firstName(colleague.full_name);
      setConfirmReq({
        title: t("{name} is already handling this chat. Take it over?", { name }),
        text: t("They will see that you took over."),
        okLabel: t("Take over"),
        onConfirm: () => run("takeover", true),
      });
    } else {
      run("takeover");
    }
  };
  const handBack = () => setConfirmReq({
    title: t("Hand this chat back to the AI?"),
    text: t("{agent} will answer the customer's next messages.", { agent }),
    okLabel: t("Hand back to AI"),
    tone: "brand",
    onConfirm: () => run("release"),
  });
  const closeChat = () => setConfirmReq({
    title: t("Close this conversation?"),
    text: t("The customer can still write again later."),
    okLabel: t("Close"),
    tone: "brand",
    onConfirm: () => run("close"),
  });

  const send = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true);
    setReplyError(null);
    try {
      const msg = await post<Message>(`/api/conversations/${id}/messages`, { content: text });
      if (msg.delivery_status === "failed") {
        setReplyError(t("Saved, but WhatsApp did not deliver it. If the customer's last message is older than 24 hours, WhatsApp only allows approved template messages."));
      }
      setText("");
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && conv.channel === "whatsapp") setWindowClosed(err.message);
      else setReplyError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const canned = [
    t("I'll call you in five minutes to take the payment."),
    t("The bank details are in your ticket."),
    t("Your seats are held until tomorrow."),
  ];
  const visible = conv.messages.filter((m) => showTools || m.kind === "text");

  return (
    <div className="chat-screen">
      <header className="chat-top">
        <button type="button" className="chat-back" onClick={() => navigate(backTo)} aria-label={t("Back")}>
          <ArrowLeft className="flip" size={21} />
        </button>
        <div className="chat-top-main">
          <h2 className="chat-name"><bdi>{customerLabel(c)}</bdi></h2>
          <div className="chat-meta">
            <Channel channel={conv.channel} />
            <span className={`pill ${p.cls}`}>{p.label}</span>
            {conv.tickets.map((tk) => (
              <Link key={tk.id} to={`/app/tickets?open=${tk.id}`} className="ref-chip" aria-label={t("Ticket {reference}", { reference: tk.reference })}>
                <Ticket aria-hidden="true" /><bdi dir="ltr">{tk.reference}</bdi>
              </Link>
            ))}
          </div>
          <div className="chat-sub">
            {c.phone && <bdi dir="ltr">{c.phone}</bdi>}
            {c.phone && c.email && " · "}
            {c.email && <bdi dir="ltr">{c.email}</bdi>}
            {(c.phone || c.email) && " · "}
            {t("started {date}", { date: dateTime(conv.created_at) })}
          </div>
          {conv.handover_reason && <div className="chat-reason" dir="auto">{trServer(conv.handover_reason)}</div>}
        </div>
        <button type="button" className={`icon-btn tool-btn ${showTools ? "on" : ""}`} aria-pressed={showTools}
          title={t("Show AI tool activity")} aria-label={t("Show AI tool activity")} onClick={() => setShowTools(!showTools)}>
          <Wrench aria-hidden="true" />
        </button>
      </header>

      <div className="chat-scroll" ref={scroller} aria-live="polite" aria-relevant="additions">
        {visible.map((m) => <StaffMessage key={m.id} m={m} customer={customerLabel(c)} agent={agent} />)}
      </div>

      <ErrorBox error={error} />
      {canReply && (
        <footer className="chat-foot">
          {expired && (
            <div className="window-box" role="note">
              <div className="window-title"><ClockCountdown aria-hidden="true" />{t("WhatsApp's 24-hour window has ended")}</div>
              <div className="window-text">
                {t("WhatsApp only allows replies within 24 hours of the customer's last message. Call the customer, or wait for them to write again.")}
              </div>
              {c.phone && (
                <a className="window-call" href={`tel:${c.phone.replace(/\s+/g, "")}`}>
                  <Phone aria-hidden="true" /><bdi dir="ltr">{c.phone}</bdi>
                </a>
              )}
            </div>
          )}
          {!mine ? (
            <>
              <button type="button" className="cv-take" disabled={!!acting} onClick={takeOver}>
                <HandGrabbing size={20} aria-hidden="true" />
                {acting === "takeover" ? t("Please wait…")
                  : colleague ? t("Take over from {name}", { name: firstName(colleague.full_name) }) : t("Take over")}
              </button>
              {conv.status !== "closed" && (
                <div className="foot-links">
                  {conv.status === "human" && (
                    <button type="button" className="foot-link" disabled={!!acting} onClick={handBack}>{t("Hand back to AI")}</button>
                  )}
                  <button type="button" className="foot-link" disabled={!!acting} onClick={closeChat}>{t("Close")}</button>
                </div>
              )}
            </>
          ) : (
            <>
              <div className="foot-actions">
                <button type="button" className="foot-btn" disabled={!!acting} onClick={handBack}>
                  <Robot aria-hidden="true" />{acting === "release" ? t("Please wait…") : t("Hand back to AI")}
                </button>
                <button type="button" className="foot-btn" disabled={!!acting} onClick={closeChat}>
                  <Check aria-hidden="true" />{acting === "close" ? t("Please wait…") : t("Close")}
                </button>
              </div>
              {!expired && (
                <>
                  <ErrorBox error={replyError} />
                  <form className="reply-row" onSubmit={send}>
                    <textarea ref={input} value={text} dir="auto" rows={1} aria-label={t("Reply")}
                      placeholder={t("Reply to the customer…")}
                      onChange={(e) => setText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          send();
                        }
                      }} />
                    <button className="send-btn" disabled={busy || !text.trim()} aria-label={busy ? t("Sending…") : t("Send")}>
                      <PaperPlaneRight weight="fill" className="flip" aria-hidden="true" />
                    </button>
                  </form>
                  <div className="canned" role="group" aria-label={t("Quick replies")}>
                    {canned.map((line) => (
                      <button key={line} type="button" className="canned-chip"
                        onClick={() => { setText(line); input.current?.focus(); }}>
                        {line}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
        </footer>
      )}
      {confirmReq && <ConfirmSheet req={confirmReq} onClose={() => setConfirmReq(null)} />}
    </div>
  );
}

const DELIVERY: Record<string, string> = { sent: "Sent", delivered: "Delivered", read: "Read", failed: "Failed" };

function StaffMessage({ m, customer, agent }: { m: Message; customer: string; agent: string }) {
  const { t } = useI18n();
  const time = new Date(m.created_at).toLocaleTimeString(currentLocale(), { hour: "numeric", minute: "2-digit" });
  if (m.sender === "system") {
    return <div className="msg-sys" dir="auto" title={dateTime(m.created_at)}><span className="msg-sys-dot" aria-hidden="true" />{trServer(m.content)}</div>;
  }
  if (m.kind === "tool_call") {
    const calls = ((m.meta?.tool_calls as { function: { name: string; arguments: string } }[]) || []);
    return (
      <div className="msg-tool" dir="ltr">
        {calls.map((c, i) => <div key={i}><Wrench aria-hidden="true" /> <strong>{c.function.name}</strong> {c.function.arguments}</div>)}
      </div>
    );
  }
  if (m.kind === "tool_result") {
    return <div className="msg-tool"><details><summary>↳ {t("result of {name}", { name: String(m.meta?.name ?? t("tool")) })}</summary><pre dir="ltr">{m.content}</pre></details></div>;
  }
  const side = m.sender === "customer" ? "in" : "out";
  const label = m.sender === "customer" ? customer : m.sender === "ai" ? t("{agent} · AI", { agent }) : m.author_name ?? t("Employee");
  const LabelIcon = m.sender === "customer" ? User : m.sender === "ai" ? Sparkle : Headset;
  const st = m.delivery_status;
  const StIcon = st === "failed" ? WarningCircle : st === "delivered" || st === "read" ? Checks : Check;
  return (
    <div className={`msg msg-${side} msg-${m.sender}`}>
      <span className="msg-label"><LabelIcon aria-hidden="true" /><bdi>{label}</bdi></span>
      <div className="msg-bubble" dir="auto"><ChatText text={m.content} /></div>
      <span className={`msg-meta ${st === "failed" ? "failed" : ""}`} title={dateTime(m.created_at)}>
        {m.sender === "agent" && st && (
          <span className="msg-status"><StIcon weight={st === "read" ? "fill" : "duotone"} aria-hidden="true" />{t(DELIVERY[st] ?? st)}</span>
        )}
        <span className="msg-time">{time}</span>
      </span>
    </div>
  );
}
