export type Role = "system_admin" | "company_admin" | "support" | "ticket_agent";

export interface DashboardBranding {
  logo: string | null;
  dashboard_color: string;
  dashboard_sidebar: string;
}

export interface CompanyBrief {
  id: number;
  name: string;
  slug: string;
  status: string;
  branding?: DashboardBranding | null;
}

export type Section = "search" | "featured" | "offers" | "how" | "about" | "contact";

/** Smaller parts of the customer page that can be hidden ("powered_by": platform owner only). */
export interface PageElements {
  kicker: boolean;
  trust: boolean;
  lang_switch: boolean;
  nav_links: boolean;
  nav_phone: boolean;
  whatsapp_icon: boolean;
  budget_filter: boolean;
  chips: boolean;
  hero_chat: boolean;
  chat_launcher: boolean;
  offers_count: boolean;
  prices_note: boolean;
  footer_note: boolean;
  powered_by: boolean;
}

export type CardStyle = "poster" | "photo" | "compact";

export interface CardDesign {
  style: CardStyle;
  columns: 2 | 3 | 4;
  show_price: boolean;
  show_duration: boolean;
  show_hotel: boolean;
  show_next_date: boolean;
  show_seats: boolean;
  show_tags: boolean;
  per_person: boolean;
  show_button: boolean;
}

/** Customer-page texts replacing the standard ones: {en: {key: text}, ar: {key: text}}. */
export type PageTexts = Record<"en" | "ar", Record<string, string>>;

export interface PublicBranding {
  primary_color: string;
  accent_color: string;
  bg_color: string | null;
  surface_color: string | null;
  text_color: string | null;
  highlight_color: string | null;
  logo: string | null;
  hero_style: "gradient" | "image" | "solid";
  hero_image: string | null;
  hero_title_en: string;
  hero_title_ar: string;
  hero_text_en: string;
  hero_text_ar: string;
  about_title_en: string;
  about_title_ar: string;
  about_en: string;
  about_ar: string;
  about_image: string | null;
  about_bg_image: string | null;
  how_bg_image: string | null;
  sections: Section[];
  elements: PageElements;
  card_style: "rounded" | "square";
  layout: "grid" | "list";
  cards: CardDesign;
  texts: PageTexts;
}

export interface Branding extends PublicBranding {
  version?: number;
  dashboard_color: string;
  dashboard_sidebar: string;
}

export interface Analytics {
  days: number;
  currency: string;
  daily: { date: string; web: number; whatsapp: number; bookings: number; booked_value: number }[];
  funnel: { conversations: number; with_booking: number; paid_or_confirmed: number };
  top_packages: { title: string; bookings: number; value: number }[];
  handled_by_ai: number;
  handed_to_team: number;
  booked_value: number;
  /** Paid and confirmed bookings. */
  paid_value: number;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  permissions: string[];
  is_active: boolean;
  company_id: number | null;
  created_at: string;
  last_login_at: string | null;
}

export interface Me extends User {
  company: CompanyBrief | null;
}

export interface UserList {
  users: User[];
  max_users: number;
  used: number;
}

export interface PermissionCatalog {
  permissions: Record<string, string>;
  role_defaults: Record<string, string[]>;
}

export interface CompanyAdmin {
  id: number;
  name: string;
  slug: string;
  status: "active" | "suspended";
  max_users: number;
  user_count: number;
  currency: string;
  contact_email: string | null;
  contact_phone: string | null;
  whatsapp_connected: boolean;
  whatsapp_phone_number_id: string | null;
  package_count: number;
  open_tickets: number;
  created_at: string;
}

export interface PlatformStats {
  companies: number;
  active_companies: number;
  users: number;
  conversations: number;
  tickets: number;
}

export interface CompanySettings {
  id: number;
  name: string;
  slug: string;
  status: string;
  max_users: number;
  currency: string;
  contact_email: string | null;
  contact_phone: string | null;
  ai_agent_name: string;
  ai_welcome_message: string | null;
  ai_welcome_message_ar: string | null;
  ai_instructions: string;
  knowledge_base: string;
  whatsapp_phone_number_id: string | null;
  whatsapp_display_number: string | null;
  whatsapp_token_set: boolean;
  whatsapp_app_secret_set: boolean;
  whatsapp_webhook_path: string | null;
  whatsapp_verify_token: string | null;
}

export interface TrainingExample {
  id: number;
  question: string;
  answer: string;
  created_at: string;
  updated_at: string;
}

export interface AICheck {
  ok: boolean;
  provider: string;
  model: string;
  fallback_models: string[];
  server: string;
  api_key_set: boolean;
  uses_tools: boolean;
  answered_by: string | null;
  message: string;
  seconds: number;
}

export interface TravelPackage {
  id: number;
  title: string;
  destination: string;
  country: string;
  description: string;
  duration_days: number;
  price_per_person: number;
  child_price: number | null;
  currency: string;
  departure_dates: string[];
  includes: string[];
  excludes: string[];
  tags: string[];
  hotel_name: string | null;
  hotel_stars: number | null;
  seats_available: number | null;
  image_url: string | null;
  is_active: boolean;
  is_featured: boolean;
  /** Seats left on each departure date ("YYYY-MM-DD"), when the package limits seats. */
  seats_left_by_date?: Record<string, number> | null;
}

export interface Customer {
  id: number;
  name: string | null;
  phone: string | null;
  email: string | null;
  whatsapp_id: string | null;
}

export interface UserBrief {
  id: number;
  full_name: string;
}

export type ConversationStatus = "ai" | "human" | "closed";

export interface Message {
  id: number;
  sender: "customer" | "ai" | "agent" | "system";
  kind: "text" | "tool_call" | "tool_result";
  content: string;
  meta: Record<string, unknown> | null;
  author_name: string | null;
  delivery_status: string | null;
  created_at: string;
}

export interface ConversationSummary {
  id: number;
  channel: "web" | "whatsapp";
  status: ConversationStatus;
  handover_reason: string | null;
  customer: Customer;
  assigned_to: UserBrief | null;
  created_at: string;
  last_message_at: string;
  last_message_preview: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: Message[];
  tickets: { id: number; reference: string; status: string }[];
}

export type TicketStatus = "pending_payment" | "in_progress" | "paid" | "confirmed" | "cancelled";

export interface Ticket {
  id: number;
  reference: string;
  status: TicketStatus;
  package_id: number | null;
  package_title: string;
  departure_date: string | null;
  adults: number;
  children: number;
  lead_traveler_name: string;
  contact_phone: string | null;
  contact_email: string | null;
  special_requests: string;
  total_price: number;
  currency: string;
  internal_notes: string;
  payment_reference: string | null;
  created_by: string;
  conversation_id: number | null;
  customer: Customer;
  assigned_to: UserBrief | null;
  created_at: string;
  updated_at: string;
  seats_held: number;
  /** The seats went back on sale because the booking was not paid in time. */
  seats_released: boolean;
}

export interface TicketEvent {
  id: number;
  actor: string;
  action: "created" | "assigned" | "unassigned" | "payment_reference" | "price" | "status" | "notes" | string;
  old_value: string | null;
  new_value: string | null;
  created_at: string;
}

export interface Dashboard {
  conversations_by_status: Record<string, number>;
  tickets_by_status: Record<string, number>;
  pipeline_value: number;
  confirmed_value: number;
  currency: string;
  /** Open or confirmed bookings in other currencies, not included in the totals. */
  other_currencies?: Record<string, number>;
  packages_active: number;
  users: number;
  max_users: number;
  conversations_waiting: number;
  my_open_tickets: number;
}

export interface PublicCompany {
  name: string;
  slug: string;
  ai_agent_name: string;
  welcome_message: string;
  currency: string;
  whatsapp_number: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  branding: PublicBranding;
}

export interface Travelers { adults: number; children: number }

/** Rich cards under an AI reply in the customer chat (built by the server from its own data). */
export type ChatCard =
  | { type: "package"; id: number; title: string; destination: string; country: string; duration_days: number;
      price_per_person: number; currency: string; image_url: string | null }
  | { type: "quote"; package: string; destination: string; departure_date: string; travelers: Travelers;
      total_price: number; currency: string }
  | { type: "ticket"; ticket_reference: string; package: string; destination: string; departure_date: string;
      travelers: Travelers; total_price: number; currency: string };

export interface PublicMessage {
  id: number;
  sender: "customer" | "ai" | "agent";
  content: string;
  created_at: string;
  cards?: ChatCard[];
}

/** One platform setting (Platform settings page). Secrets never carry a value, only whether they are set. */
export interface PlatformSettingValue {
  key: string;
  secret: boolean;
  /** Saved on the settings page; null = not saved there (the Render environment variable is used). */
  value: string | boolean | null;
  saved: boolean;
  env_value: string | boolean | null;
  env_set: boolean;
  effective: string | boolean | null;
  effective_set: boolean;
  source: "database" | "environment";
  updated_at: string | null;
  updated_by: string | null;
}

export interface PlatformSettings {
  ai: Record<string, PlatformSettingValue>;
  whatsapp: Record<string, PlatformSettingValue>;
  webhook_path: string;
  info: {
    version: string;
    commit: string | null;
    database: string;
    environment: string;
    demo_data: boolean;
    companies: number;
  };
}

// --- AI training (import, test chat, knowledge) and WhatsApp connection -------------------

export interface TrainingImportResult {
  added: number;
  preview: boolean;
  rows: { line: number; question: string; answer: string }[];
  duplicates: { line: number; question: string }[];
  problems: { line: number; error: string }[];
}

export interface TryPackage {
  id: number;
  title: string | null;
  destination: string | null;
  country: string | null;
  duration_days: number | null;
  price_per_person: number | null;
  currency: string | null;
  image_url: string | null;
}

export interface TryAIResult {
  ok: boolean;
  reply: string | null;
  error: string | null;
  used_answers: { id: number; question: string; answer: string }[];
  packages: TryPackage[];
  tools: string[];
  simulated: string[];
}

export interface AIKnowledge {
  ai_agent_name: string;
  ai_welcome_message: string | null;
  ai_welcome_message_ar: string | null;
  ai_instructions: string;
  knowledge_base: string;
  examples: number;
}

export type WhatsAppConnectionStatus = "connected" | "not_connected" | "needs_app_secret" | "needs_token";

export interface WhatsAppStatus {
  status: WhatsAppConnectionStatus;
  mode: "own" | "platform" | "none";
  phone_number_id: string | null;
  display_number: string | null;
  token_set: boolean;
  app_secret_set: boolean;
  platform_available: boolean;
  webhook_path: string | null;
  verify_token: string | null;
}

export interface WhatsAppTestResult {
  result: "connected" | "token_invalid" | "number_not_found" | "no_access" | "network" | "not_configured";
  message: string;
  display_number: string | null;
  verified_name: string | null;
  status: WhatsAppStatus;
}
