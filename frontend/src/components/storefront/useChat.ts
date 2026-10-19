import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, get, post } from "../../api";
import type { Lang } from "../Money";
import type { StorefrontText } from "../../i18n";
import type { PublicCompany, PublicMessage } from "../../types";

interface ChatReply { status: string; messages: PublicMessage[] }
interface StartReply extends ChatReply { token: string }

export interface QuickReply { label: string; message: string }

/** A saved chat is resumed only within a day of the visitor's last message (shared devices). */
const RESUME_MS = 24 * 60 * 60 * 1000;

interface SavedChat { token: string; at: number }

function readSaved(key: string): string | null {
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? "null") as SavedChat | null;
    if (saved && typeof saved.token === "string" && typeof saved.at === "number" && Date.now() - saved.at < RESUME_MS) {
      return saved.token;
    }
    localStorage.removeItem(key); // too old, or saved by an older version without a time
  } catch { /* storage unavailable or not JSON */ }
  return null;
}

function writeSaved(key: string, token: string) {
  try { localStorage.setItem(key, JSON.stringify({ token, at: Date.now() } satisfies SavedChat)); } catch { /* storage unavailable */ }
}

/**
 * One conversation per visitor and agency, shared by every chat view on the page (phone screen,
 * desktop hero card, floating widget). The conversation is created on the server only when the
 * visitor opens or uses the chat; before that the welcome message is shown locally.
 * A previous conversation on this device is resumed from localStorage, but only if the visitor
 * wrote within the last day, so the next person on a shared device doesn't see it.
 */
export function useChat({ slug, company, lang, t, active, offline = false }: {
  slug: string;
  company: PublicCompany;
  lang: Lang;
  t: StorefrontText;
  /** Poll for staff replies only while a chat view is on screen. */
  active: boolean;
  /** Editor preview: show the welcome only, never create or resume a conversation. */
  offline?: boolean;
}) {
  const storageKey = `travel_chat_${slug}`;
  const base = `/api/public/companies/${slug}/chats`;
  const [token, setToken] = useState<string | null>(null);
  const [messages, setMessages] = useState<PublicMessage[]>([]);
  const [status, setStatus] = useState("ai");
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [ready, setReady] = useState(false);
  const starting = useRef<Promise<string> | null>(null);
  const tokenRef = useRef<string | null>(null);
  const busy = useRef(false);
  const queued = useRef<string[]>([]);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  const merge = useCallback((incoming: PublicMessage[]) => {
    setMessages((prev) => {
      const kept = prev.filter((m) => m.id > 0);
      const known = new Set(kept.map((m) => m.id));
      return [...kept, ...incoming.filter((m) => !known.has(m.id))].sort((a, b) => a.id - b.id);
    });
  }, []);

  const startNew = useCallback((): Promise<string> => {
    if (starting.current) return starting.current;
    const p = post<StartReply>(base, { lang }).then((res) => {
      writeSaved(storageKey, res.token);
      tokenRef.current = res.token;
      setToken(res.token);
      setStatus(res.status);
      setMessages(res.messages);
      return res.token;
    }).finally(() => { starting.current = null; });
    starting.current = p;
    return p;
  }, [base, storageKey, lang]);

  // Resume the previous chat on this device (if any).
  useEffect(() => {
    const saved = offline ? null : readSaved(storageKey);
    if (!saved) { setReady(true); return; }
    let cancelled = false;
    get<ChatReply>(`${base}/${saved}/messages?after_id=0`)
      .then((r) => {
        if (cancelled) return;
        tokenRef.current = saved;
        setToken(saved);
        setStatus(r.status);
        setMessages(r.messages);
      })
      .catch(() => { try { localStorage.removeItem(storageKey); } catch { /* ignore */ } })
      .finally(() => { if (!cancelled) setReady(true); });
    return () => { cancelled = true; };
  }, [base, storageKey, offline]);

  /** Make sure a conversation exists (called when a chat view opens or gets focus). */
  const ensure = useCallback(() => {
    if (tokenRef.current || !ready || offline) return;
    startNew().catch(() => setError(t.notSent));
  }, [ready, startNew, t, offline]);

  // Pick up replies written by employees, every 5 s while the page is visible.
  useEffect(() => {
    if (!token || !active) return;
    const id = window.setInterval(() => {
      if (busy.current || document.visibilityState !== "visible") return;
      const last = messagesRef.current.filter((m) => m.id > 0).slice(-1)[0]?.id ?? 0;
      get<ChatReply>(`${base}/${token}/messages?after_id=${last}`)
        .then((r) => { setStatus(r.status); if (r.messages.length) merge(r.messages); })
        .catch(() => {});
    }, 5000);
    return () => window.clearInterval(id);
  }, [token, active, base, merge]);

  const send = useCallback(async (raw: string) => {
    const content = raw.trim();
    if (!content || offline) return;
    if (busy.current) { queued.current.push(content); return; }
    busy.current = true;
    setError(null);
    setFailed(null);
    setWaiting(true);
    let next: string | undefined = content;
    while (next) {
      const text: string = next;
      setMessages((prev) => [...prev, { id: -Date.now(), sender: "customer", content: text, created_at: new Date().toISOString() }]);
      try {
        const tk = tokenRef.current ?? await startNew();
        const r = await post<ChatReply>(`${base}/${tk}/messages`, { content: text });
        writeSaved(storageKey, tk);
        setStatus(r.status);
        merge(r.messages);
        next = queued.current.shift();
      } catch (e) {
        setMessages((prev) => prev.filter((m) => m.id > 0));
        setError(e instanceof ApiError && e.status === 429 ? t.tooFast : t.notSent);
        setFailed(text);
        setDraft((d) => d || text);
        queued.current = [];
        next = undefined;
      }
    }
    busy.current = false;
    setWaiting(false);
  }, [base, storageKey, merge, startNew, t, offline]);

  const retry = useCallback(() => {
    if (!failed) return;
    const text = failed;
    setDraft((d) => (d.trim() === text ? "" : d));
    send(text);
  }, [failed, send]);

  const restart = useCallback(() => {
    if (offline) return;
    try { localStorage.removeItem(storageKey); } catch { /* ignore */ }
    tokenRef.current = null;
    setToken(null);
    setMessages([]);
    setStatus("ai");
    setError(null);
    setFailed(null);
    startNew().catch(() => setError(t.notSent));
  }, [storageKey, startNew, t, offline]);

  // Before the conversation exists, the welcome message is shown locally.
  const shown = useMemo<PublicMessage[]>(() => {
    if (messages.length || token) return messages;
    // The agency's own welcome text from the page editor wins over the AI settings' welcome.
    const own = company.branding.texts?.[lang]?.welcome?.trim();
    const welcome = !own && lang === "en" && company.welcome_message ? company.welcome_message : t.welcome(company.ai_agent_name, company.name);
    return [{ id: 0, sender: "ai", content: welcome, created_at: "" }];
  }, [messages, token, lang, company, t]);

  const hasCustomer = messages.some((m) => m.sender === "customer");
  const human = status === "human";

  // The booking summary still waiting for an answer (no customer message after it).
  const lastQuote = (() => {
    for (let i = shown.length - 1; i >= 0; i--) {
      const m = shown[i];
      if (m.sender === "customer") return -1;
      if (m.cards?.some((c) => c.type === "quote")) return m.id;
    }
    return -1;
  })();
  const activeQuoteId = human ? -1 : lastQuote;

  let quick: QuickReply[] = [];
  if (!waiting && !human) {
    if (!hasCustomer) {
      quick = [t.qHoney, t.qFamily, t.qHuman].map((x) => ({ label: x, message: x }));
    } else if (activeQuoteId !== -1) {
      quick = [{ label: t.confirmBooking, message: t.yesConfirm }, { label: t.change, message: t.changeMsg }];
    }
  }

  return {
    token, messages: shown, status, human, waiting, error, failed, draft, setDraft,
    ensure, send, retry, restart, hasCustomer, quick, activeQuoteId,
  };
}

export type ChatEngine = ReturnType<typeof useChat>;
