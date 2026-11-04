/** Sends errors of this browser to the server (POST /api/client-errors), so the platform owner sees on
 *  System health what fails on the live site. Only the page path, the API path (never the query string),
 *  the status and a short message are sent; never form contents, tokens or passwords.
 *  Reports are throttled here as well as on the server, and a failed report is never reported. */

const TOKEN_KEY = "travel_ai_token";
const MAX_PER_MINUTE = 8;
const SAME_MESSAGE_MS = 60_000;

export type ClientErrorKind = "error" | "unhandledrejection" | "crash" | "api" | "network" | "bad_response" | "poll";

export interface ClientErrorReport {
  kind: ClientErrorKind;
  message: string;
  apiPath?: string;
  method?: string;
  status?: number;
}

const sentAt: number[] = [];
const lastByKey = new Map<string, number>();

function buildTime(): string {
  try {
    return __BUILD_TIME__;
  } catch {
    return "";
  }
}

const pathOnly = (p: string) => p.split("?")[0].split("#")[0].slice(0, 300);

export function reportClientError(report: ClientErrorReport): void {
  try {
    const now = Date.now();
    const key = `${report.kind}|${report.method ?? ""}|${report.apiPath ?? ""}|${report.status ?? ""}|${report.message.slice(0, 120)}`;
    const last = lastByKey.get(key);
    if (last && now - last < SAME_MESSAGE_MS) return;
    while (sentAt.length && now - sentAt[0] > 60_000) sentAt.shift();
    if (sentAt.length >= MAX_PER_MINUTE) return;
    sentAt.push(now);
    lastByKey.set(key, now);
    if (lastByKey.size > 200) lastByKey.clear();

    const headers: Record<string, string> = { "Content-Type": "application/json" };
    let token: string | null = null;
    try { token = localStorage.getItem(TOKEN_KEY); } catch { /* storage blocked */ }
    if (token) headers.Authorization = `Bearer ${token}`;
    const body = JSON.stringify({
      kind: report.kind,
      message: (report.message || "").slice(0, 900),
      page: pathOnly(window.location.pathname),
      api_path: report.apiPath ? pathOnly(report.apiPath) : null,
      method: report.method ?? null,
      status: report.status ?? null,
      build: buildTime().slice(0, 60) || null,
    });
    void fetch("/api/client-errors", { method: "POST", headers, body, keepalive: true }).catch(() => { /* never report a report */ });
  } catch {
    /* error reporting must never break the page */
  }
}

function errorText(value: unknown): string {
  if (value instanceof Error) return `${value.name}: ${value.message}`;
  if (typeof value === "string") return value;
  try { return JSON.stringify(value).slice(0, 300); } catch { return String(value); }
}

let installed = false;

/** window.onerror and unhandled promise rejections (API errors are reported by api.ts itself). */
export function installGlobalErrorHandlers(): void {
  if (installed) return;
  installed = true;
  window.addEventListener("error", (e: ErrorEvent) => {
    // Errors of browser extensions and cross-origin scripts carry no details: not ours.
    if (!e.message || e.message === "Script error.") return;
    const where = e.filename ? ` (${pathOnly(e.filename).split("/").pop()}:${e.lineno})` : "";
    reportClientError({ kind: "error", message: `${e.message}${where}` });
  });
  window.addEventListener("unhandledrejection", (e: PromiseRejectionEvent) => {
    const reason = e.reason as { status?: number; reported?: boolean } | undefined;
    if (reason && reason.reported) return; // an API error that api.ts already sent
    reportClientError({ kind: "unhandledrejection", message: errorText(e.reason) });
  });
}

export function reportCrash(error: unknown): void {
  reportClientError({ kind: "crash", message: errorText(error) });
}

/** Background polling may fail now and then (a phone losing signal): stay quiet, but tell the server
 *  after `after` failures in a row. Call ok() after a success. */
export function pollWatcher(name: string, after = 3) {
  let failures = 0;
  return {
    ok() { failures = 0; },
    fail(err: unknown) {
      failures += 1;
      if (failures === after) {
        const status = (err as { status?: number } | null)?.status;
        reportClientError({ kind: "poll", message: `${name}: ${after} failures in a row: ${errorText(err)}`, status });
      }
    },
  };
}
