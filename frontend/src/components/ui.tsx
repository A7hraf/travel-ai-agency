import { MouseEvent, ReactNode, useEffect, useId, useRef, useState } from "react";
import { tr } from "../lang";
import { X } from "./Icon";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Dialog window. With `dirty`, closing (Escape, ×, a tap on the background) first asks
 * whether to discard the changes. Keyboard focus stays inside while it is open.
 */
export function Modal({ title, onClose, children, wide, dirty }: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
  dirty?: boolean;
}) {
  const titleId = useId();
  const box = useRef<HTMLDivElement>(null);
  const downOnBackdrop = useRef(false);
  // Refs so the effects below run once per opening (re-running would move the focus).
  const latest = useRef({ onClose, dirty });
  latest.current = { onClose, dirty };

  const requestClose = () => {
    if (latest.current.dirty && !window.confirm(tr("Discard your changes?"))) return;
    latest.current.onClose();
  };

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const el = box.current;
    const first = el?.querySelector<HTMLElement>(
      '.modal-body input:not([disabled]):not([type="hidden"]):not([type="checkbox"]):not([type="file"]), .modal-body select:not([disabled]), .modal-body textarea:not([disabled])',
    );
    (first ?? el)?.focus({ preventScroll: true });

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        requestClose();
        return;
      }
      if (e.key !== "Tab" || !el) return;
      const items = [...el.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((x) => x.offsetParent !== null);
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const firstItem = items[0];
      const lastItem = items[items.length - 1];
      if (!el.contains(document.activeElement)) {
        e.preventDefault();
        firstItem.focus();
      } else if (e.shiftKey && document.activeElement === firstItem) {
        e.preventDefault();
        lastItem.focus();
      } else if (!e.shiftKey && document.activeElement === lastItem) {
        e.preventDefault();
        firstItem.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (previous && document.contains(previous)) previous.focus({ preventScroll: true });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Close on a background tap only when the press started AND ended on the background
  // (selecting text in a field and releasing outside must not close the form).
  const onBackdropDown = (e: MouseEvent) => { downOnBackdrop.current = e.target === e.currentTarget; };
  const onBackdropClick = (e: MouseEvent) => {
    if (downOnBackdrop.current && e.target === e.currentTarget) requestClose();
    downOnBackdrop.current = false;
  };

  return (
    <div className="modal-backdrop" onMouseDown={onBackdropDown} onClick={onBackdropClick}>
      <div ref={box} className={`modal ${wide ? "modal-wide" : ""}`} role="dialog" aria-modal="true"
        aria-labelledby={titleId} tabIndex={-1}>
        <div className="sheet-grip" aria-hidden="true" />
        <div className="modal-head">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="icon-btn" onClick={requestClose} aria-label={tr("Close")}><X size={20} /></button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function Badge({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

/** A failed load or save, in words. With `onRetry` it also offers to try again. */
export function ErrorBox({ error, onRetry }: { error: string | null; onRetry?: () => void }) {
  if (!error) return null;
  if (!onRetry) return <div className="error-box">{error}</div>;
  return (
    <div className="error-box error-retry" role="alert">
      <span>{error}</span>
      <button type="button" className="btn btn-sm" onClick={onRetry}>{tr("Retry")}</button>
    </div>
  );
}

/** Shown while a page or a card waits for the server: a spinner with "Loading…", a skeleton, and after
 *  8 seconds a note that a sleeping server can take up to a minute to wake up. */
export function Loading({ height = 220, label, compact }: { height?: number; label?: string; compact?: boolean }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const id = window.setTimeout(() => setSlow(true), 8000);
    return () => window.clearTimeout(id);
  }, []);
  return (
    <div className={`load-state ${compact ? "compact" : ""}`} role="status" aria-live="polite">
      <div className="load-line"><span className="load-spinner" aria-hidden="true" />{label ?? tr("Loading…")}</div>
      {slow && <p className="load-slow">{tr("Still loading — the server may be waking up. This can take up to a minute.")}</p>}
      {height > 0 && <div className="skeleton load-skel" style={{ height }} aria-hidden="true" />}
    </div>
  );
}

/** Loading, then the data, or the error with a Retry button. */
export function LoadGate<T>({ data, error, onRetry, height, label, children }: {
  data: T | null | undefined;
  error: string | null | undefined;
  onRetry?: () => void;
  height?: number;
  label?: string;
  children: (data: T) => ReactNode;
}) {
  if (data !== null && data !== undefined) return <>{children(data)}</>;
  if (error) return <ErrorBox error={error} onRetry={onRetry} />;
  return <Loading height={height} label={label} />;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

/** Renders chat text: line breaks and WhatsApp-style *bold*, without injecting HTML. */
export function ChatText({ text }: { text: string }) {
  return (
    <>
      {text.split("\n").map((line, i) => (
        <span key={i}>
          {i > 0 && <br />}
          {line.split(/(\*[^*\n]+\*)/g).map((part, j) =>
            part.length > 2 && part.startsWith("*") && part.endsWith("*") ? (
              <strong key={j}>{part.slice(1, -1)}</strong>
            ) : (
              <span key={j}>{part}</span>
            ),
          )}
        </span>
      ))}
    </>
  );
}

export const TICKET_TONES: Record<string, string> = {
  pending_payment: "amber",
  in_progress: "blue",
  paid: "teal",
  confirmed: "green",
  cancelled: "gray",
};

export const CONVERSATION_TONES: Record<string, string> = { ai: "teal", human: "amber", closed: "gray" };
