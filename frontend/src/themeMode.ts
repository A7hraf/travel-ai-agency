/**
 * Light / Dark / Auto for the staff app. The choice is kept per browser (localStorage, default Auto);
 * Auto follows the device (prefers-color-scheme) and changes live when the device switches.
 * The active theme is written to <html data-theme="light|dark"> plus the color-scheme and theme-color
 * meta tags. main.tsx imports this module first, so the attribute is set before the first render
 * (the CSP allows no inline script in index.html).
 */
import { useSyncExternalStore } from "react";
import type { Theme } from "./theme";

export type ThemeMode = "light" | "dark" | "auto";
export const THEME_MODES: ThemeMode[] = ["light", "dark", "auto"];

const STORAGE_KEY = "ghanjah_theme";
/** Browser bar colour per theme (the page background). */
const BAR: Record<Theme, string> = { light: "#f3f2f2", dark: "#201e1d" };

function readMode(): ThemeMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "light" || v === "dark" || v === "auto") return v;
  } catch {
    /* storage unavailable (private window, blocked) */
  }
  return "auto";
}

const media: MediaQueryList | null =
  typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia("(prefers-color-scheme: dark)") : null;

let mode: ThemeMode = readMode();
/** A page that has its own design (the customer page) pins a theme while it is shown. */
let pinned: Theme | null = typeof location !== "undefined" && location.pathname.startsWith("/c/") ? "dark" : null;
let snapshot = { mode, theme: resolve() };
const listeners = new Set<() => void>();

function resolve(): Theme {
  if (pinned) return pinned;
  if (mode === "auto") return media && !media.matches ? "light" : "dark";
  return mode;
}

function meta(name: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[name="${name}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.name = name;
    document.head.appendChild(el);
  }
  el.content = content;
}

function apply() {
  const theme = resolve();
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
  meta("color-scheme", theme);
  meta("theme-color", BAR[theme]);
  if (snapshot.mode !== mode || snapshot.theme !== theme) {
    snapshot = { mode, theme };
    listeners.forEach((fn) => fn());
  }
}

export function setThemeMode(next: ThemeMode) {
  mode = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* not saved: the choice lasts until the page is reloaded */
  }
  apply();
}

/** Show `theme` while a page with its own colours is open; returns the function that ends it. */
export function pinTheme(theme: Theme): () => void {
  pinned = theme;
  apply();
  return () => {
    pinned = null;
    apply();
  };
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** The chosen mode, the theme in use (Auto resolved) and the setter. */
export function useTheme(): { mode: ThemeMode; theme: Theme; setMode: (m: ThemeMode) => void } {
  const s = useSyncExternalStore(subscribe, () => snapshot, () => snapshot);
  return { mode: s.mode, theme: s.theme, setMode: setThemeMode };
}

// Set the theme now, before React renders anything.
if (typeof document !== "undefined") {
  apply();
  const onDevice = () => {
    if (mode === "auto") apply();
  };
  if (media) {
    if (typeof media.addEventListener === "function") media.addEventListener("change", onDevice);
    else media.addListener?.(onDevice);
  }
  // Another tab changed the choice.
  window.addEventListener("storage", (e) => {
    if (e.key === STORAGE_KEY) {
      mode = readMode();
      apply();
    }
  });
}
