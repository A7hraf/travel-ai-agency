import { Children, type ReactNode, useEffect, useRef, useState } from "react";
import type { StorefrontText } from "../../i18n";
import { Pause, Play } from "../Icon";

const REST_MS = 1400; // after a finger lets go, the strip waits before moving again

/**
 * A row of cards that moves slowly by itself. It pauses while the pointer is over it, while a card has the
 * keyboard focus, while a finger scrolls it and with the pause button; a mouse can drag it and fingers scroll it
 * natively. It only moves while on screen, and not at all for visitors who ask for less motion.
 */
export function Marquee({ children, label, t, secondsPerCard = 3.5 }: {
  children: ReactNode; label: string; t: StorefrontText; secondsPerCard?: number;
}) {
  const box = useRef<HTMLDivElement>(null);
  const group = useRef<HTMLDivElement>(null);
  const [paused, setPaused] = useState(false);
  const [dragging, setDragging] = useState(false);
  const cards = Children.toArray(children);
  // Enough cards to cover a wide screen, so the seam never shows.
  const repeat = Math.max(1, Math.ceil(8 / Math.max(cards.length, 1)));
  const row = Array.from({ length: repeat }, () => cards).flat();
  const count = row.length;
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  // Copies are only there for the seamless loop: no focus, no screen reader.
  useEffect(() => {
    box.current?.querySelectorAll<HTMLElement>("[data-copy]").forEach((n) => { n.inert = true; });
  });

  useEffect(() => {
    const el = box.current;
    const g = group.current;
    if (!el || !g || count === 0) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let last = 0;
    let visible = false;
    let hover = false;
    let focused = false;
    let touching = false;
    let restUntil = 0;
    let pos = el.scrollLeft;
    let drag: { x: number; left: number; moved: boolean } | null = null;

    const period = () => g.offsetWidth; // one copy of the cards, gap included
    const wrap = () => {
      const p = period();
      if (p <= 0) return;
      if (el.scrollLeft >= p) el.scrollLeft -= p;
      else if (el.scrollLeft <= 0 && (touching || drag)) el.scrollLeft += p;
    };
    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      const dt = last ? Math.min(64, now - last) : 0;
      last = now;
      const still = pausedRef.current || !visible || hover || focused || touching || drag || now < restUntil || reduced.matches;
      if (still) {
        wrap();
        pos = el.scrollLeft;
        return;
      }
      const p = period();
      pos += (p / (count * secondsPerCard * 1000)) * dt;
      if (pos >= p) pos -= p;
      el.scrollLeft = pos;
    };
    frame = requestAnimationFrame(tick);

    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; }, { threshold: 0 });
    io.observe(el);
    const onEnter = (e: PointerEvent) => { if (e.pointerType === "mouse") hover = true; };
    const onLeave = (e: PointerEvent) => { if (e.pointerType === "mouse") hover = false; };
    const onFocusIn = () => { focused = el.matches(":focus-within") && !!document.querySelector(":focus-visible"); };
    const onFocusOut = () => { requestAnimationFrame(() => { focused = el.matches(":focus-within"); }); };
    const onTouchStart = () => { touching = true; };
    const onTouchEnd = () => { touching = false; restUntil = performance.now() + REST_MS; };
    // Dragging with a mouse; fingers keep the browser's own scrolling with momentum.
    const onDown = (e: PointerEvent) => {
      if (e.pointerType !== "mouse" || e.button !== 0) return;
      drag = { x: e.clientX, left: el.scrollLeft, moved: false };
    };
    const onMove = (e: PointerEvent) => {
      if (!drag) return;
      const dx = e.clientX - drag.x;
      if (!drag.moved && Math.abs(dx) > 4) {
        drag.moved = true;
        setDragging(true);
        el.setPointerCapture(e.pointerId);
      }
      if (drag.moved) {
        el.scrollLeft = drag.left - dx;
        wrap();
      }
    };
    const onUp = (e: PointerEvent) => {
      if (!drag) return;
      const moved = drag.moved;
      drag = null;
      setDragging(false);
      if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
      if (moved) {
        // A drag is not a click on the card under the pointer.
        const stop = (ev: Event) => { ev.stopPropagation(); ev.preventDefault(); };
        el.addEventListener("click", stop, { capture: true, once: true });
        setTimeout(() => el.removeEventListener("click", stop, { capture: true }), 0);
      }
    };
    el.addEventListener("pointerenter", onEnter);
    el.addEventListener("pointerleave", onLeave);
    el.addEventListener("focusin", onFocusIn);
    el.addEventListener("focusout", onFocusOut);
    el.addEventListener("touchstart", onTouchStart, { passive: true });
    el.addEventListener("touchend", onTouchEnd, { passive: true });
    el.addEventListener("touchcancel", onTouchEnd, { passive: true });
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointercancel", onUp);
    el.addEventListener("scroll", wrap, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      io.disconnect();
      el.removeEventListener("pointerenter", onEnter);
      el.removeEventListener("pointerleave", onLeave);
      el.removeEventListener("focusin", onFocusIn);
      el.removeEventListener("focusout", onFocusOut);
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchend", onTouchEnd);
      el.removeEventListener("touchcancel", onTouchEnd);
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerup", onUp);
      el.removeEventListener("pointercancel", onUp);
      el.removeEventListener("scroll", wrap);
    };
  }, [count, secondsPerCard]);

  if (count === 0) return null;
  return (
    <div className="ed-marquee-wrap">
      {/* Always left-to-right underneath, so the movement is the same in both languages. */}
      <div ref={box} className={`ed-marquee ${dragging ? "is-dragging" : ""}`} dir="ltr" role="region" aria-label={label}>
        <div ref={group} className="ed-marquee-group" role="list">
          {row.map((c, i) => (
            <div key={i} role={i < cards.length ? "listitem" : undefined} className="ed-marquee-card"
              data-copy={i >= cards.length || undefined} aria-hidden={i >= cards.length || undefined}>{c}</div>
          ))}
        </div>
        <div className="ed-marquee-group" aria-hidden="true" data-copy>
          {row.map((c, i) => <div key={i} className="ed-marquee-card">{c}</div>)}
        </div>
      </div>
      <div className="ed-marquee-controls">
        <button type="button" className="ed-motion" aria-pressed={paused} aria-label={paused ? t.edPlay : t.edPause} onClick={() => setPaused(!paused)}>
          {paused ? <Play weight="fill" /> : <Pause weight="fill" />}
        </button>
      </div>
    </div>
  );
}
