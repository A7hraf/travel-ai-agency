/** Subscription plans: API types and small helpers shared by the console and the company pages. */
import { shortDate } from "./util";

export interface Plan {
  id: number;
  name: string;
  name_ar: string;
  description: string;
  description_ar: string;
  features: string[];
  features_ar: string[];
  price_monthly: number;
  price_yearly: number;
  trial_days: number;
  max_users: number;
  max_packages: number | null;
  max_ai_conversations: number | null;
  allow_whatsapp: boolean;
  allow_instagram: boolean;
  allow_page_editor: boolean;
  allow_remove_powered_by: boolean;
  priority_support: boolean;
  is_default: boolean;
  is_archived: boolean;
  sort_order: number;
  companies: number;
}

export interface Usage {
  users: number;
  max_users: number | null;
  packages: number;
  max_packages: number | null;
  ai_conversations: number;
  max_ai_conversations: number | null;
}

export type BillingCycle = "monthly" | "yearly";
export type SubStatus = "trial" | "active" | "past_due" | "expired" | "cancelled";
/** The status combined with today's date ("grace": period over, still working). */
export type SubState = SubStatus | "grace";

export interface Subscription {
  company_id: number;
  plan: Plan;
  billing_cycle: BillingCycle;
  status: SubStatus;
  state: SubState;
  current_period_start: string | null;
  current_period_end: string | null;
  trial_end: string | null;
  ends_on: string | null;
  days_left: number | null;
  grace_until: string | null;
  custom_price: number | null;
  cycle_price: number;
  monthly_value: number;
  notes: string;
  max_users: number;
  max_users_custom: boolean;
  usage: Usage;
  next_period: { start: string; end: string; amount: number };
  payments_total: number;
}

export interface SubscriptionBrief {
  company_id: number;
  plan_id: number;
  plan_name: string;
  plan_name_ar: string;
  billing_cycle: BillingCycle;
  status: SubStatus;
  state: SubState;
  ends_on: string | null;
  days_left: number | null;
  monthly_value: number;
}

export interface Payment {
  id: number;
  company_id: number;
  invoice_number: string;
  amount: number;
  currency: string;
  paid_on: string;
  method: "bank_transfer" | "card" | "cash";
  reference: string;
  period_start: string | null;
  period_end: string | null;
  plan_name: string;
  billing_cycle: BillingCycle;
  notes: string;
  created_by: string | null;
  created_at: string;
}

export interface Invoice {
  payment: Payment;
  company: { name: string; slug: string; contact_email: string | null; contact_phone: string | null };
}

export interface BillingOverview {
  mrr: number;
  currency: string;
  counts: Record<string, number>;
  expiring_soon: number;
  grace_days: number;
}

export interface CompanyPlan {
  plan: Plan;
  billing_cycle: BillingCycle;
  status: SubStatus;
  state: SubState;
  ends_on: string | null;
  days_left: number | null;
  grace_until: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  trial_end: string | null;
  cycle_price: number;
  usage: Usage;
  payments: Payment[];
  payments_total: number;
}

export interface PlanNotice {
  has_plan: boolean;
  plan_name: string;
  plan_name_ar: string;
  status: SubStatus;
  state: SubState;
  ends_on: string | null;
  days_left: number | null;
  grace_until: string | null;
  banner: "trial_ending" | "past_due" | "expired" | "cancelled" | null;
  whatsapp: boolean;
  instagram: boolean;
  page_editor: boolean;
  remove_powered_by: boolean;
  max_packages: number | null;
  max_ai_conversations: number | null;
}

export const STATE_LABELS: Record<SubState, string> = {
  trial: "Trial",
  active: "Active [plan]",
  past_due: "Payment due",
  grace: "Grace period",
  expired: "Expired",
  cancelled: "Cancelled [plan]",
};

export const STATE_TONES: Record<SubState, string> = {
  trial: "cyan",
  active: "on",
  past_due: "warn",
  grace: "warn",
  expired: "bad",
  cancelled: "off",
};

export const STATUS_OPTIONS: SubStatus[] = ["trial", "active", "past_due", "expired", "cancelled"];

export const METHOD_LABELS: Record<Payment["method"], string> = {
  bank_transfer: "Bank transfer",
  card: "Card",
  cash: "Cash",
};

export const CYCLE_LABELS: Record<BillingCycle, string> = { monthly: "Monthly", yearly: "Yearly" };

export const planName = (p: { name: string; name_ar?: string }, lang: string) =>
  (lang === "ar" && p.name_ar) || p.name;

export const planFeatures = (p: Plan, lang: string) =>
  lang === "ar" && p.features_ar.length ? p.features_ar : p.features;

export const planDescription = (p: Plan, lang: string) =>
  (lang === "ar" && p.description_ar) || p.description;

export const periodText = (start: string | null, end: string | null) =>
  start && end ? `${shortDate(start)} – ${shortDate(end)}` : end ? shortDate(end) : "—";
