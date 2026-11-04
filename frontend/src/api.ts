import { reportClientError } from "./errorReporter";
import { tr, trServer } from "./lang";

const TOKEN_KEY = "travel_ai_token";

export class ApiError extends Error {
  status: number;
  /** Already sent to System health (the global handler does not send it again). */
  reported = false;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export interface ApiOptions {
  /** Background polling: failures are not reported one by one (see pollWatcher in errorReporter.ts). */
  quiet?: boolean;
}

/** Failed requests the owner should see on System health: server errors, the server not answering,
 *  and failed page loads (GET 4xx such as 403/404 loops; 401 is just an ended session). */
/** A request that gets no answer fails after a while, so a page shows an error instead of loading forever.
 *  (A sleeping free server can take up to a minute to wake up, hence the generous limit.) */
const REQUEST_TIMEOUT_MS = 75_000;
function fetchWithTimeout(input: string, init: RequestInit, ms = REQUEST_TIMEOUT_MS): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(new DOMException("timeout", "TimeoutError")), ms);
  return fetch(input, { ...init, signal: ctrl.signal }).finally(() => clearTimeout(timer));
}

function shouldReport(method: string, status: number): boolean {
  if (status === 0 || status >= 500) return true;
  // 401 = signed out, 423 = a customer page paused by its plan: both expected, not faults.
  return method === "GET" && status >= 400 && status !== 401 && status !== 423;
}

/** The server's own (English) text, so the same error reads the same in every language. */
function rawDetail(data: unknown): string | undefined {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    try { return JSON.stringify(detail).slice(0, 400); } catch { return undefined; }
  }
  return undefined;
}

function report(err: ApiError, method: string, path: string, opts?: ApiOptions, raw?: string): ApiError {
  if (!opts?.quiet && shouldReport(method, err.status)) {
    const kind = err.status === 0 ? "network" : err.status === 200 ? "bad_response" : "api";
    const fallback = kind === "network" ? "No answer from the server (network error)"
      : kind === "bad_response" ? "Answer was not JSON (an HTML page or an old version?)" : `HTTP ${err.status}`;
    reportClientError({ kind, message: raw ?? fallback, apiPath: path, method, status: err.status });
    err.reported = true;
  }
  return err;
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable */
  }
}

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

/** Field names of the API, as people know them on the forms. */
const FIELD_LABELS: Record<string, string> = {
  title: "Title",
  destination: "Destination",
  country: "Country",
  description: "Description",
  duration_days: "Duration (days)",
  price_per_person: "Price per adult",
  child_price: "Price per child",
  currency: "Currency",
  departure_dates: "Departure dates",
  hotel_name: "Hotel",
  hotel_stars: "Hotel stars",
  seats_available: "Seats available",
  image_url: "Package photo",
  name: "Name",
  full_name: "Full name",
  admin_full_name: "Full name",
  email: "Email",
  admin_email: "Email (login)",
  contact_email: "Contact email",
  contact_phone: "Contact phone",
  password: "Password",
  new_password: "New password",
  current_password: "Current password",
  admin_password: "Password",
  slug: "Web address",
  max_users: "Account limit",
  question: "Customer question",
  answer: "Your company's answer",
  content: "Message",
  ai_agent_name: "Agent name",
  ai_welcome_message: "Welcome message (English)",
  ai_welcome_message_ar: "Welcome message (Arabic)",
  ai_instructions: "Extra instructions",
  knowledge_base: "Knowledge & policies",
  whatsapp_phone_number_id: "Phone number ID",
  whatsapp_display_number: "Public WhatsApp number",
  payment_reference: "Payment reference",
  total_price: "Total price",
  internal_notes: "Internal notes",
  role: "Role",
  status: "Status",
};

interface ValidationItem {
  loc?: (string | number)[];
  type?: string;
  msg?: string;
  ctx?: Record<string, unknown>;
}

/** One FastAPI/pydantic validation error -> one sentence in the person's language. */
function validationSentence(d: ValidationItem): string {
  const key = [...(d.loc ?? [])].reverse().find((x) => typeof x === "string" && x !== "body") as string | undefined;
  const field = key ? tr(FIELD_LABELS[key] ?? key.replace(/_/g, " ")) : "";
  const ctx = d.ctx ?? {};
  const n = (k: string) => String(ctx[k] ?? "");
  const msg = (d.msg ?? "").replace(/^Value error, /, "");
  switch (d.type) {
    case "missing":
      return tr("{field} is required", { field });
    case "string_too_short":
      return tr("{field} must have at least {n} characters", { field, n: n("min_length") });
    case "string_too_long":
      return tr("{field} can have at most {n} characters", { field, n: n("max_length") });
    case "too_long":
      return tr("{field} has too many items", { field });
    case "greater_than":
      return tr("{field} must be greater than {n}", { field, n: n("gt") });
    case "greater_than_equal":
      return tr("{field} must be at least {n}", { field, n: n("ge") });
    case "less_than":
      return tr("{field} must be less than {n}", { field, n: n("lt") });
    case "less_than_equal":
      return tr("{field} must be at most {n}", { field, n: n("le") });
    case "int_parsing":
    case "int_from_float":
      return tr("{field} must be a whole number", { field });
    case "float_parsing":
    case "decimal_parsing":
      return tr("{field} must be a number", { field });
    case "date_parsing":
    case "date_from_datetime_parsing":
      return tr("{field} is not a valid date", { field });
    case "enum":
    case "literal_error":
      return tr("{field} has an invalid value", { field });
    case "string_pattern_mismatch":
      if (key === "currency") return tr("Currency must be 3 English letters, for example OMR");
      return tr("{field} has an invalid format", { field });
    case "value_error":
      if (/email/i.test(msg)) return tr("Enter a valid email address");
      return trServer(msg);
  }
  return field ? `${field}: ${trServer(msg)}` : trServer(msg);
}

function errorMessage(status: number, body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return trServer(detail);
    if (Array.isArray(detail)) {
      return [...new Set((detail as ValidationItem[]).map(validationSentence))].join("\n");
    }
  }
  if (status === 429) return tr("Too many requests, please wait a moment");
  if (status >= 500) return tr("Something went wrong on the server ({status}). Please try again.", { status });
  return tr("Request failed ({status})", { status });
}

export async function api<T = unknown>(method: string, path: string, body?: unknown, opts?: ApiOptions): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetchWithTimeout(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch (err) {
    const timedOut = err instanceof DOMException && err.name === "TimeoutError";
    throw report(new ApiError(0, timedOut
      ? tr("The server did not answer in time. Please try again in a moment.")
      : tr("Could not reach the server. Check your internet connection and try again.")), method, path, opts);
  }
  if (res.status === 204) return undefined as T;
  const raw = await res.text().catch(() => "");
  let data: unknown = null;
  let parsed = raw.trim() === "";
  if (!parsed) {
    try { data = JSON.parse(raw); parsed = true; } catch { data = null; }
  }
  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized();
    throw report(new ApiError(res.status, errorMessage(res.status, data)), method, path, opts, rawDetail(data));
  }
  if (!parsed) {
    // A web page instead of data (for example a proxy or an old version answering): never show it as
    // an empty page.
    throw report(new ApiError(200, tr("The server sent an unexpected answer. Reload the page; if it happens again, the platform owner can see it on System health.")), method, path, opts);
  }
  return data as T;
}

/** Downloads a file of the API (CSV exports) with the login, and saves it under `filename`. */
export async function download(path: string, filename: string): Promise<void> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetchWithTimeout(path, { headers }, 120_000);
  } catch {
    throw report(new ApiError(0, tr("Could not reach the server. Check your internet connection and try again.")), "GET", path);
  }
  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized();
    const data = await res.json().catch(() => null);
    throw report(new ApiError(res.status, errorMessage(res.status, data)), "GET", path, undefined, rawDetail(data));
  }
  const blob = await res.blob();
  const match = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "");
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = match?.[1] ?? filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const get = <T>(path: string, opts?: ApiOptions) => api<T>("GET", path, undefined, opts);
export const post = <T>(path: string, body?: unknown) => api<T>("POST", path, body ?? {});
export const patch = <T>(path: string, body: unknown) => api<T>("PATCH", path, body);
export const put = <T>(path: string, body: unknown) => api<T>("PUT", path, body);
export const del = (path: string) => api<void>("DELETE", path);
