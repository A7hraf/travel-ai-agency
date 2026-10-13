import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError, get, post } from "../api";
import { useAuth } from "../auth";
import { Badge, ChatText, CONVERSATION_TONES, Empty, ErrorBox } from "../components/ui";
import { trServer, useI18n } from "../lang";
import type { ConversationDetail, ConversationSummary, Message } from "../types";
import { CONVERSATION_STATUS_LABELS, customerLabel, dateTime, DELIVERY_LABELS, timeAgo, usePolling } from "../util";

const FILTERS = [
  { value: "", label: "All" },
  { value: "human", label: "Needs a human" },
  { value: "ai", label: "AI handling" },
  { value: "closed", label: "Closed" },
];

/** "With Sara" when a colleague handles the chat, otherwise the status label. */
function StatusBadge({ c }: { c: ConversationSummary }) {
  const { t } = useI18n();
  const label = c.status === "human" && c.assigned_to
    ? t("With {name}", { name: c.assigned_to.full_name })
    : t(CONVERSATION_STATUS_LABELS[c.status]);
  return <Badge tone={CONVERSATION_TONES[c.status]}>{label}</Badge>;
}

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

export default function Conversations() {
  const { id } = useParams();
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const [search, setSearch] = useState("");
  const [list, setList] = useState<ConversationSummary[] | null>(null);

  usePolling(() => {
    const q = new URLSearchParams();
    if (status) q.set("status", status);
    if (search.trim()) q.set("q", search.trim());
    get<ConversationSummary[]>(`/api/conversations?${q}`).then(setList).catch(() => {});
  }, 5000, [status, search]);

  return (
    <div className="split">
      <div className="split-list">
        <div className="split-list-head">
          <h1>{t("Conversations")}</h1>
          <div className="tabs">
            {FILTERS.map((f) => (
              <button key={f.value} className={`tab ${status === f.value ? "active" : ""}`} aria-pressed={status === f.value}
                onClick={() => setParams(f.value ? { status: f.value } : {})}>
                {t(f.label)}
              </button>
            ))}
          </div>
          <input placeholder={t("Search name, phone, email")} aria-label={t("Search name, phone, email")} value={search}
            onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="conv-list">
          {list === null && <div className="loading">{t("Loading…")}</div>}
          {list?.length === 0 && <Empty>{status || search.trim() ? t("No results for this filter.") : t("No conversations yet.")}</Empty>}
          {list?.map((c) => (
            <Link key={c.id} to={`/app/conversations/${c.id}${status ? `?status=${status}` : ""}`}
              className={`conv-item ${String(c.id) === id ? "selected" : ""}`}>
              <div className="row-between">
                <strong><bdi>{customerLabel(c.customer)}</bdi></strong>
                <span className="muted small">{timeAgo(c.last_message_at)}</span>
              </div>
              <div className="conv-preview" dir="auto">{trServer(c.last_message_preview) || "…"}</div>
              <div className="conv-tags">
                <StatusBadge c={c} />
                <span className="channel">{c.channel === "whatsapp" ? `🟢 ${t("WhatsApp")}` : `🌐 ${t("Web")}`}</span>
              </div>
            </Link>
          ))}
        </div>
      </div>
      <div className="split-detail">
        {id ? <ConversationView key={id} id={Number(id)} /> : <Empty>{t("Select a conversation to see the chat.")}</Empty>}
      </div>
    </div>
  );
}

function ConversationView({ id }: { id: number }) {
  const { can } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [conv, setConv] = useState<ConversationDetail | null>(null);
  const [showTools, setShowTools] = useState(false);
  // The reply draft survives a reload or a new login (per conversation, this browser tab only).
  const [text, setTextState] = useState(() => readDraft(id));
  const [error, setError] = useState<string | null>(null);
  const [replyError, setReplyError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [acting, setActing] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
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

  useEffect(() => {
    if (conv && conv.messages.length !== lastCount.current) {
      lastCount.current = conv.messages.length;
      bottom.current?.scrollIntoView({ block: "end" });
    }
  }, [conv]);

  if (!conv) return <div className="loading">{t("Loading…")}</div>;

  const action = async (path: "takeover" | "release" | "close") => {
    if (acting) return;
    if (path === "close" && !confirm(t("Close this conversation? If the customer writes again it reopens with the AI."))) return;
    if (path === "release" && !confirm(t("Hand this conversation back to the AI? The AI answers the customer's next message."))) return;
    setError(null);
    setActing(path);
    try {
      try {
        setConv(await post<ConversationDetail>(`/api/conversations/${id}/${path}`));
      } catch (e) {
        // A colleague already handles it: ask before taking it from them.
        if (path === "takeover" && e instanceof ApiError && e.status === 409) {
          if (!confirm(t("{message}. Do you want to take it over anyway?", { message: e.message.replace(/\.$/, "") }))) return;
          setConv(await post<ConversationDetail>(`/api/conversations/${id}/takeover?force=true`));
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

  const send = async (e: FormEvent) => {
    e.preventDefault();
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
      setReplyError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const visible = conv.messages.filter((m) => showTools || m.kind === "text");
  const c = conv.customer;

  return (
    <div className="chat-panel">
      <div className="chat-head">
        <div>
          <h2><bdi>{customerLabel(c)}</bdi></h2>
          <div className="muted small">
            {conv.channel === "whatsapp" ? t("WhatsApp") : t("Website chat")}
            {c.phone && <> · <bdi dir="ltr">{c.phone}</bdi></>}
            {c.email && <> · <bdi dir="ltr">{c.email}</bdi></>}
            {" · "}{t("started {date}", { date: dateTime(conv.created_at) })}
          </div>
          <div className="conv-tags">
            <StatusBadge c={conv} />
            {conv.handover_reason && <span className="muted small" dir="auto">{trServer(conv.handover_reason)}</span>}
            {conv.tickets.map((tk) => (
              <Link key={tk.id} to={`/app/tickets?open=${tk.id}`} className="ticket-chip">🎫 <bdi dir="ltr">{tk.reference}</bdi></Link>
            ))}
          </div>
        </div>
        {can("conversations.reply") && (
          <div className="chat-actions">
            {conv.status !== "human" && (
              <button className="btn btn-sm" disabled={!!acting} onClick={() => action("takeover")}>
                {acting === "takeover" ? t("Please wait…") : t("Take over")}
              </button>
            )}
            {conv.status !== "ai" && (
              <button className="btn btn-sm" disabled={!!acting} onClick={() => action("release")}>
                {acting === "release" ? t("Please wait…") : t("Hand back to AI")}
              </button>
            )}
            {conv.status !== "closed" && (
              <button className="btn btn-sm btn-ghost" disabled={!!acting} onClick={() => action("close")}>
                {acting === "close" ? t("Please wait…") : t("Close")}
              </button>
            )}
          </div>
        )}
      </div>
      <ErrorBox error={error} />

      <label className="tool-toggle small">
        <input type="checkbox" checked={showTools} onChange={(e) => setShowTools(e.target.checked)} /> {t("Show AI tool activity")}
      </label>

      <div className="chat-messages">
        {visible.map((m) => <StaffMessage key={m.id} m={m} />)}
        <div ref={bottom} />
      </div>

      {can("conversations.reply") && conv.status !== "closed" && (
        <>
          <ErrorBox error={replyError} />
          <form className="chat-input" onSubmit={send}>
            <textarea
              value={text}
              dir="auto"
              aria-label={t("Reply")}
              placeholder={conv.status === "ai" ? t("Writing here takes the chat over from the AI…") : t("Write to the customer…")}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  (e.currentTarget.form as HTMLFormElement).requestSubmit();
                }
              }}
            />
            <button className="btn btn-primary" disabled={busy || !text.trim()}>{busy ? t("Sending…") : t("Send")}</button>
          </form>
        </>
      )}
    </div>
  );
}

function StaffMessage({ m }: { m: Message }) {
  const { t } = useI18n();
  if (m.sender === "system") return <div className="msg-system" dir="auto">{trServer(m.content)} · {timeAgo(m.created_at)}</div>;
  if (m.kind === "tool_call") {
    const calls = ((m.meta?.tool_calls as { function: { name: string; arguments: string } }[]) || []);
    return (
      <div className="msg-tool" dir="ltr">
        {calls.map((c, i) => <div key={i}>🔧 <strong>{c.function.name}</strong> {c.function.arguments}</div>)}
      </div>
    );
  }
  if (m.kind === "tool_result") {
    return <div className="msg-tool"><details><summary>↳ {t("result of {name}", { name: String(m.meta?.name ?? t("tool")) })}</summary><pre dir="ltr">{m.content}</pre></details></div>;
  }
  const who = m.sender === "customer" ? t("Customer") : m.sender === "ai" ? t("AI agent") : m.author_name ?? t("Employee");
  return (
    <div className={`msg msg-${m.sender}`}>
      <div className="msg-who">{who}</div>
      <div className="msg-bubble" dir="auto"><ChatText text={m.content} /></div>
      <div className="msg-time">
        {dateTime(m.created_at)}
        {m.delivery_status && ` · ${t(DELIVERY_LABELS[m.delivery_status] ?? m.delivery_status)}`}
      </div>
    </div>
  );
}
