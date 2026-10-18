import { ReactNode, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useI18n } from "../../lang";

/** 0 → 1 over one second (ease-out cubic), restarted every time `key` changes (and not null).
 *  Used for the dashboard count-up on enter and on period change. Respects reduced motion. */
export function useCountUp(key: unknown, ms = 1000): number {
  const [a, setA] = useState(0);
  useEffect(() => {
    if (key === null || key === undefined) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setA(1);
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / ms);
      setA(1 - Math.pow(1 - p, 3));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    setA(0);
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [key, ms]);
  return a;
}

/** Page title of the agency workspace and the platform console: kicker, 44 px title, subtitle, actions. */
export function PageTitle({ kicker, title, subtitle, actions, live }: {
  kicker?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  live?: boolean;
}) {
  return (
    <header className="ad-head">
      <div className="ad-head-text">
        {kicker && <div className={`ad-kicker ${live ? "live" : ""}`}>{kicker}</div>}
        <h1 className="ad-title">{title}</h1>
        {subtitle && <p className="ad-sub">{subtitle}</p>}
      </div>
      {actions && <div className="ad-actions">{actions}</div>}
    </header>
  );
}

/** On/off switch (a real checkbox underneath, so it works with the keyboard and screen readers). */
export function Switch({ checked, onChange, label, hint, disabled }: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: ReactNode;
  hint?: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className={`ad-switch ${disabled ? "disabled" : ""}`}>
      <input type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="ad-switch-track" aria-hidden="true"><span /></span>
      <span className="ad-switch-text">
        <span>{label}</span>
        {hint && <small>{hint}</small>}
      </span>
    </label>
  );
}

/** Confirm bottom sheet (centred dialog on desktop): title, text, Cancel and a coloured confirm button.
 *  Opens above an open Modal too: it takes the keyboard (Escape, Tab) while it is shown. */
export function ConfirmSheet({ title, text, confirmLabel, tone = "primary", busy, onConfirm, onCancel, children, confirmDisabled }: {
  title: string;
  text?: ReactNode;
  confirmLabel: string;
  tone?: "primary" | "accent" | "danger";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  children?: ReactNode;
  confirmDisabled?: boolean;
}) {
  const { t } = useI18n();
  const box = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const latest = useRef(onCancel);
  latest.current = onCancel;

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const el = box.current;
    const first = el?.querySelector<HTMLElement>("input:not([disabled])") ?? el?.querySelector<HTMLElement>(".ad-sheet-actions .btn");
    first?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => {
      if (!el) return;
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        latest.current();
        return;
      }
      if (e.key !== "Tab") return;
      e.stopPropagation();
      const items = [...el.querySelectorAll<HTMLElement>("button:not([disabled]), input:not([disabled]), a[href]")];
      if (!items.length) return;
      const a = items[0];
      const z = items[items.length - 1];
      if (!el.contains(document.activeElement)) { e.preventDefault(); a.focus(); }
      else if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus(); }
      else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
    };
    // Capture phase: runs before the Modal's own window listener.
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      if (previous && document.contains(previous)) previous.focus({ preventScroll: true });
    };
  }, []);

  return createPortal(
    <div className="ad-sheet-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onCancel(); }}>
      <div ref={box} className="ad-sheet" role="alertdialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="sheet-grip" aria-hidden="true" />
        <h2 id={titleId}>{title}</h2>
        {text && <p className="ad-sheet-text">{text}</p>}
        {children}
        <div className="ad-sheet-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={busy}>{t("Cancel")}</button>
          <button type="button" className={`btn ${tone === "danger" ? "btn-danger" : tone === "accent" ? "btn-accent" : "btn-primary"}`}
            onClick={onConfirm} disabled={busy || confirmDisabled}>{confirmLabel}</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** Initials for avatars ("Amira Al Balushi" → "AA"). */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "?";
}

/** A stable hue per name (company avatars). */
export function hueOf(text: string): number {
  let h = 0;
  for (const ch of text) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}
