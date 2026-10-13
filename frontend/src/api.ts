import { tr, trServer } from "./lang";

const TOKEN_KEY = "travel_ai_token";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
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

export async function api<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, tr("Could not reach the server. Check your internet connection and try again."));
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized();
    throw new ApiError(res.status, errorMessage(res.status, data));
  }
  return data as T;
}

export const get = <T>(path: string) => api<T>("GET", path);
export const post = <T>(path: string, body?: unknown) => api<T>("POST", path, body ?? {});
export const patch = <T>(path: string, body: unknown) => api<T>("PATCH", path, body);
export const put = <T>(path: string, body: unknown) => api<T>("PUT", path, body);
export const del = (path: string) => api<void>("DELETE", path);
