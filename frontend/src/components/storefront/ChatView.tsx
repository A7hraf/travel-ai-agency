import { FormEvent, ReactNode, RefObject, useEffect, useRef } from "react";
import { ArrowClockwise, Headset, PaperPlaneRight, X } from "../Icon";
import type { Lang } from "../Money";
import { ChatText } from "../ui";
import type { StorefrontText } from "../../i18n";
import type { PublicCompany, TravelPackage } from "../../types";
import { ChatPackageCard, ChatQuoteCard, ChatTicketCard } from "./ChatCards";
import type { ChatEngine } from "./useChat";

/** Round avatar of the AI consultant (agency accent), or of the team (magenta) once a person has taken over. */
export function ChatAvatar({ company, human, size = 42, dot = true }: { company: PublicCompany; human: boolean; size?: number; dot?: boolean }) {
  return (
    <span className={`sf-avatar ${human ? "sf-human" : ""}`} style={{ width: size, height: size, fontSize: size * 0.43 }} aria-hidden="true">
      {human ? <Headset weight="fill" /> : company.ai_agent_name.trim().charAt(0).toUpperCase()}
      {dot && <span className="sf-avatar-dot" />}
    </span>
  );
}

/** Title and subtitle of the chat (AI consultant, or "a travel consultant is with you"). */
export function ChatTitle({ company, human, t }: { company: PublicCompany; human: boolean; t: StorefrontText }) {
  return (
    <div className="sf-chat-title">
      <div className="sf-chat-name">{human ? t.consultant : company.ai_agent_name} · {company.name}</div>
      <div className={`sf-chat-sub ${human ? "sf-human" : ""}`}>{human ? t.humanSub : t.aiSub}</div>
    </div>
  );
}

/** Header used by the phone chat screen and the floating widget. */
export function ChatHeader({ company, chat, t, onClose, onNew, compact }: {
  company: PublicCompany; chat: ChatEngine; t: StorefrontText; onClose: () => void; onNew: () => void; compact?: boolean;
}) {
  return (
    <div className={`sf-chat-head ${compact ? "sf-compact" : ""}`}>
      {!compact && <button type="button" className="sf-round-btn" onClick={onClose} aria-label={t.close}><X /></button>}
      <ChatAvatar company={company} human={chat.human} size={compact ? 40 : 42} />
      <ChatTitle company={company} human={chat.human} t={t} />
      <button type="button" className="sf-round-btn" onClick={onNew} aria-label={t.newChat} title={t.newChat}><ArrowClockwise /></button>
      {compact && <button type="button" className="sf-round-btn sf-filled" onClick={onClose} aria-label={t.close}><X /></button>}
    </div>
  );
}

/**
 * Messages, rich cards, quick replies and the message box. Every view of the chat on the page
 * renders this with the same engine, so they all show the same conversation.
 */
export function ChatView({ chat, t, lang, packages, onViewPackage, inputRef, live, size = "md", placeholder, onFocus, footer }: {
  chat: ChatEngine;
  t: StorefrontText;
  lang: Lang;
  packages: TravelPackage[];
  onViewPackage: (p: TravelPackage) => void;
  inputRef?: RefObject<HTMLInputElement>;
  /** Announce new messages to screen readers (only one view on screen should). */
  live: boolean;
  size?: "md" | "sm";
  placeholder?: string;
  onFocus?: () => void;
  footer?: ReactNode;
}) {
  const body = useRef<HTMLDivElement>(null);
  const ownInput = useRef<HTMLInputElement>(null);
  const input = inputRef ?? ownInput;

  // Keep the newest message in view (scrolls this list only, never the page).
  useEffect(() => {
    const el = body.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [chat.messages, chat.waiting, chat.error]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const text = chat.draft.trim();
    if (!text || chat.waiting) return;
    chat.setDraft("");
    chat.send(text);
  };
  const bookCard = (title: string, days: number) => chat.send(t.interested(title, days));

  return (
    <>
      <div ref={body} className={`sf-chat-body sf-${size}`} aria-live={live ? "polite" : undefined} aria-relevant="additions">
        {chat.messages.map((m) => {
          if (m.sender === "customer") {
            return <div key={m.id} className="sf-bubble sf-me" dir="auto">{m.content}</div>;
          }
          if (m.sender === "agent") {
            return (
              <div key={m.id} className="sf-staff">
                <span className="sf-staff-who"><Headset />{t.consultant}</span>
                <div className="sf-bubble sf-staff" dir="auto"><ChatText text={m.content} /></div>
              </div>
            );
          }
          return (
            <div key={m.id} className="sf-ai-group">
              {m.content.trim() && <div className="sf-bubble sf-ai" dir="auto"><ChatText text={m.content} /></div>}
              {m.cards?.map((card, i) => {
                if (card.type === "package") {
                  const pkg = packages.find((p) => p.id === card.id);
                  return (
                    <ChatPackageCard key={i} card={card} t={t} lang={lang} disabled={chat.waiting}
                      onView={pkg ? () => onViewPackage(pkg) : undefined}
                      onBook={() => bookCard(card.title, card.duration_days)} />
                  );
                }
                if (card.type === "quote") {
                  return (
                    <ChatQuoteCard key={i} card={card} t={t} lang={lang} active={chat.activeQuoteId === m.id} disabled={chat.waiting}
                      onConfirm={() => chat.send(t.yesConfirm)} onChange={() => chat.send(t.changeMsg)} />
                  );
                }
                if (card.type === "ticket") return <ChatTicketCard key={i} card={card} t={t} />;
                return null;
              })}
            </div>
          );
        })}
        {chat.waiting && !chat.human && (
          <div className="sf-bubble sf-ai sf-typing" aria-hidden="true"><span className="typing-dots"><i /><i /><i /></span></div>
        )}
        {chat.error && (
          <div className="sf-chat-error" role="alert">
            <span>{chat.error}</span>
            {chat.failed && <button type="button" className="link-btn" onClick={chat.retry} disabled={chat.waiting}>{t.retry}</button>}
          </div>
        )}
      </div>
      {chat.quick.length > 0 && (
        <div className={`sf-quick sf-${size}`}>
          {chat.quick.map((q) => (
            <button key={q.label} type="button" dir="auto" onClick={() => chat.send(q.message)} disabled={chat.waiting}>{q.label}</button>
          ))}
        </div>
      )}
      <form className={`sf-chat-form sf-${size}`} onSubmit={submit}>
        <input ref={input} value={chat.draft} onChange={(e) => chat.setDraft(e.target.value)} onFocus={onFocus}
          placeholder={placeholder ?? t.typeHere} aria-label={t.messageLabel} maxLength={2000} dir="auto" enterKeyHint="send" />
        <button type="submit" className="sf-send" aria-label={t.send} disabled={!chat.draft.trim() || chat.waiting}>
          <PaperPlaneRight weight="fill" className="flip" />
        </button>
      </form>
      {footer}
    </>
  );
}
