import { MouseEvent, ReactNode, RefObject, useEffect, useId, useRef, useState } from "react";
import { useI18n } from "../../lang";
import { ArrowLeft, X } from "../Icon";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Open layers, newest last: only the top one reacts to Escape and Tab. */
const stack: string[] = [];

/**
 * Focus handling for a layer (sheet, panel): focus moves inside when it opens, Tab stays inside,
 * Escape asks to close it, and focus goes back to where it was when it closes.
 */
export function useLayerFocus(box: RefObject<HTMLElement>, onEscape: () => void, initial?: string) {
  const id = useId();
  const latest = useRef(onEscape);
  latest.current = onEscape;
  useEffect(() => {
    stack.push(id);
    const previous = document.activeElement as HTMLElement | null;
    const el = box.current;
    const first = (initial && el?.querySelector<HTMLElement>(initial)) || null;
    (first ?? el)?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => {
      if (stack[stack.length - 1] !== id || !el) return;
      if (e.key === "Escape") {
        e.preventDefault();
        latest.current();
        return;
      }
      if (e.key !== "Tab") return;
      const items = [...el.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((x) => x.offsetParent !== null);
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const a = items[0];
      const z = items[items.length - 1];
      if (!el.contains(document.activeElement)) {
        e.preventDefault();
        a.focus();
      } else if (e.shiftKey && document.activeElement === a) {
        e.preventDefault();
        z.focus();
      } else if (!e.shiftKey && document.activeElement === z) {
        e.preventDefault();
        a.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      const i = stack.indexOf(id);
      if (i >= 0) stack.splice(i, 1);
      if (previous && document.contains(previous)) previous.focus({ preventScroll: true });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

/** Bottom sheet on #2a2726 with a grip and a blurred backdrop (a centred card on wide screens). */
export function Sheet({ label, onClose, children, className = "" }: {
  label: string;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const downOnBackdrop = useRef(false);
  useLayerFocus(box, onClose);
  const onDown = (e: MouseEvent) => { downOnBackdrop.current = e.target === e.currentTarget; };
  const onClick = (e: MouseEvent) => {
    if (downOnBackdrop.current && e.target === e.currentTarget) onClose();
    downOnBackdrop.current = false;
  };
  return (
    <div className="gs-backdrop" onMouseDown={onDown} onClick={onClick}>
      <div ref={box} className={`gs-sheet ${className}`} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1}>
        <div className="gs-grip" aria-hidden="true" />
        {children}
      </div>
    </div>
  );
}

export interface ConfirmRequest {
  title: string;
  text?: string;
  okLabel: string;
  tone?: "accent" | "brand";
  onConfirm: () => void | Promise<void>;
}

/** "Are you sure?" sheet: Cancel and a coloured confirm button. */
export function ConfirmSheet({ req, onClose }: { req: ConfirmRequest; onClose: () => void }) {
  const { t } = useI18n();
  const box = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const [busy, setBusy] = useState(false);
  useLayerFocus(box, onClose, ".gs-confirm-ok");
  const ok = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await req.onConfirm();
    } finally {
      setBusy(false);
      onClose();
    }
  };
  return (
    <div className="gs-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={box} className="gs-sheet gs-confirm" role="alertdialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
        <div className="gs-grip" aria-hidden="true" />
        <div className="gs-confirm-title" id={titleId}>{req.title}</div>
        {req.text && <div className="gs-confirm-text">{req.text}</div>}
        <div className="gs-confirm-actions">
          <button type="button" className="gs-confirm-btn" onClick={onClose}>{t("Cancel")}</button>
          <button type="button" className={`gs-confirm-btn gs-confirm-ok ${req.tone === "brand" ? "brand" : "accent"}`}
            disabled={busy} onClick={ok}>
            {busy ? t("Please wait…") : req.okLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Detail screen: full screen and pushed in from the inline end on phones (above the tab bar),
 * a side panel with a backdrop on wide screens.
 */
export function PushPanel({ backLabel, title, onClose, children, labelledBy }: {
  backLabel: string;
  title?: string;
  onClose: () => void;
  children: ReactNode;
  labelledBy?: string;
}) {
  const { t } = useI18n();
  const box = useRef<HTMLDivElement>(null);
  useLayerFocus(box, onClose);
  return (
    <div className="gp-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={box} className="gp-panel" role="dialog" aria-modal="true" aria-labelledby={labelledBy} tabIndex={-1}>
        <div className="gp-head">
          <button type="button" className="gp-back" onClick={onClose} aria-label={t("Back")}>
            <ArrowLeft className="flip" size={21} />
          </button>
          <span className="gp-back-label">{backLabel}</span>
          {title && <span className="gp-title">{title}</span>}
          <button type="button" className="icon-btn gp-close" onClick={onClose} aria-label={t("Close")}><X size={20} /></button>
        </div>
        <div className="gp-body">{children}</div>
      </div>
    </div>
  );
}
