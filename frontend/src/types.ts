export type Role = "system_admin" | "company_admin" | "support" | "ticket_agent" | "partner";

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
  /** Business accounts (clients and vendors) switched on by the platform owner. */
  b2b_enabled?: boolean;
  /** Advanced features switched on by the platform owner (e.g. "members"). */
  addons?: string[];
  /** Members community levels (when switched on): key → names and whether their chats are priority. */
  member_levels?: Record<MemberLevel, { name_en: string; name_ar: string; priority: boolean }> | null;
  currency?: string;
}

export type MemberLevel = "level1" | "level2" | "level3" | "vip";
export const MEMBER_LEVELS: MemberLevel[] = ["level1", "level2", "level3", "vip"];

export interface LevelConfig {
  name_en: string; name_ar: string; perks_en: string; perks_ar: string; special_requests: boolean; priority: boolean;
}
export interface MembershipConfig { levels: Record<MemberLevel, LevelConfig>; show_on_page: boolean }
export interface MemberRow { customer_id: number; name: string | null; phone: string | null; email: string | null; level: MemberLevel; member_since: string | null; note: string | null }
export interface MemberList { members: MemberRow[]; counts: Record<MemberLevel, number>; config: MembershipConfig }
export interface PublicMemberLevel { key: MemberLevel; name_en: string; name_ar: string; perks_en: string[]; perks_ar: string[] }

export type PartnerKind = "client" | "vendor";

/** What the platform owner allows a travel company for its business accounts. */
export interface B2BSettings {
  enabled: boolean;
  max_clients: number;
  max_vendors: number;
  max_users_per_partner: number;
  features: string[];
}

export interface B2BOverview {
  settings: B2BSettings;
  usage: { clients: number; vendors: number };
  /** Feature key ("client.requests") → English label. */
  catalog: Record<string, string>;
}

export interface PartnerLogin {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface Partner {
  id: number;
  kind: PartnerKind;
  name: string;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  notes: string | null;
  features: string[];
  active_features: string[];
  whatsapp_numbers: string[];
  is_active: boolean;
  created_at: string;
  logins: PartnerLogin[];
}

export interface PartnerList extends B2BOverview {
  partners: Partner[];
}

export interface PartnerHome {
  partner_id: number;
  partner_name: string;
  kind: PartnerKind;
  company_name: string;
  company_slug: string;
  logo: string | null;
  features: string[];
  catalog: Record<string, string>;
  whatsapp_numbers: string[];
  company_whatsapp: string | null;
}

export type Section = "search" | "featured" | "offers" | "how" | "about" | "contact"
  | "brand" | "experiences" | "services" | "leadership" | "community";

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

export type StoryKey = "brand" | "experiences" | "services" | "leadership" | "community";

/** One card of a story section: a brand pillar, an experience, a service, a leader or a member perk. */
export interface StoryItem {
  tag_en: string; tag_ar: string;
  title_en: string; title_ar: string;
  subtitle_en: string; subtitle_ar: string;
  text_en: string; text_ar: string;
  image: string | null;
}

export interface StorySection {
  kicker_en: string; kicker_ar: string;
  title_en: string; title_ar: string;
  intro_en: string; intro_ar: string;
  image: string | null;
  items: StoryItem[];
}

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
  stories: Partial<Record<StoryKey, StorySection>>;
}

export interface Branding extends PublicBranding {
  version?: number;
  dashboard_color: string;
  dashboard_sidebar: string;
}

export interface Analytics {
  days: number;
  currency: string;
  daily: { date: string; web: number; whatsapp: number; instagram?: number; bookings: number; booked_value: number }[];
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
  whatsapp_number?: string | null;
  ai_features?: string[] | null;
}

export interface Me extends User {
  company: CompanyBrief | null;
  /** Set for the logins of a business client or vendor. */
  partner?: { id: number; name: string; kind: PartnerKind } | null;
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
  instagram_account_id?: string | null;
  instagram_username?: string | null;
  instagram_token_set?: boolean;
  instagram_app_secret_set?: boolean;
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
  member_level?: MemberLevel | null;
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
  channel: "web" | "whatsapp" | "instagram";
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

export type TicketStatus = "new" | "quoted" | "changes" | "chosen" | "final" | "rejected"
  | "pending_payment" | "in_progress" | "paid" | "working" | "confirmed" | "completed" | "cancelled";

export type ServicePart = "flight" | "hotel" | "transport" | "activity" | "food" | "visa" | "insurance" | "other";

/** One choice of a request. Cost and AI estimate are for staff only. */
export interface TicketOption {
  id: number; category: ServicePart; title: string; provider: string | null; link: string | null; details: string | null;
  cost_price: number | null; price: number | null; estimate_price: number | null; ai_reason: string | null;
  added_by: "staff" | "ai" | "vendor"; sent_to_client: boolean; chosen: boolean;
  supplier_id: number | null; image_url: string | null;
}

export interface Supplier {
  id: number; category: ServicePart; name: string; place: string; stars: number | null; link: string | null; image_url: string | null;
  description: string; notes: string; usual_cost: string | number | null; usual_price: string | number | null;
  preferred: boolean; is_active: boolean; bookings: number;
}

export interface ServiceField { key: string; label_en: string; label_ar: string; type: string; required: boolean; choices: string[] }
export interface ServiceStep { key: string; label_en: string; label_ar: string }
export interface ServiceDoc { key: string; label_en: string; label_ar: string; required: boolean; per_traveller: boolean }

export interface Service {
  id: number; key: string | null; position: number;
  name_en: string; name_ar: string; description_en: string; description_ar: string;
  pricing: "fixed" | "dynamic" | "packages"; price: string | number | null; price_note: string;
  parts: ServicePart[]; fields: ServiceField[]; steps: ServiceStep[]; documents: ServiceDoc[]; rules: string; is_active: boolean;
  /** The steps of its requests; workflow_custom is false while it follows the built-in default. */
  workflow: WorkflowStep[]; workflow_custom?: boolean;
}

export type StepType = "intake" | "review" | "quote" | "documents" | "payment" | "schedule" | "booking" | "delivery"
  | "trip" | "feedback" | "task";
export interface WorkflowStep {
  key: string; type: StepType; label_en: string; label_ar: string;
  pay_mode?: "percent" | "fixed" | "rest" | null; pay_value?: number | string | null;
  /** On one request only. */
  state?: "pending" | "active" | "done" | "skipped"; started_at?: string; done_at?: string; by?: string; note?: string;
  client_times?: string; appointment?: { at: string; text: string; location: string }; confirmed_at?: string | null;
}
export interface Installment { key: string; label_en: string; label_ar: string; amount: number; through: number; state?: string; covered: boolean }
export interface CloseInfo { by: "client" | "team"; name: string; reason: string; step: string | null; step_en: string | null; step_ar: string | null; at: string }
export interface Process { steps: WorkflowStep[]; installments: Installment[]; due_now: number | null; cancel: CloseInfo | null }

export type Stage = "quote" | "client" | "payment" | "booking" | "confirmed" | "closed";
export interface TicketMoney {
  total: number; choices_total: number; cost: number | null; cost_from: "manual" | "choices" | null;
  profit: number | null; margin_pct: number | null; paid: number; balance: number | null; pending_proofs: number;
}
export interface TicketPayment {
  id: number; amount: number | null; method: "bank_transfer" | "cash" | "card" | "link" | "other"; reference: string | null;
  file_id: number | null; status: "pending" | "approved" | "rejected"; note: string | null; created_by: string;
  reviewed_by: string | null; reviewed_at: string | null; created_at: string;
}
export interface ClientDoc { key: string; label_en: string; label_ar: string; required: boolean; need: number; have: number; done: boolean; files: number[] }
export interface PlanDay { day: number; title: string; details: string; date?: string }
export interface PipelineSummary {
  stages: Record<Stage, number>; urgent: number; unassigned: number; proofs_to_check: number;
  pipeline_value: number; to_collect: number; sales_this_month: number; profit_this_month: number; currency: string;
}

export interface RequestFile {
  id: number; key: string; kind: "payment_proof" | "client_file" | "document"; name: string; content_type: string; size: number;
  uploaded_by: string; sent_at: string | null; created_at: string; requirement?: string | null;
}

export interface Ticket {
  id: number;
  reference: string;
  status: TicketStatus;
  package_id: number | null;
  package_title: string;
  service: { id: number; key: string | null; name_en: string; name_ar: string; pricing: string; steps: ServiceStep[] } | null;
  answers: Record<string, string> | null;
  parts: ServicePart[] | null;
  destination: string | null;
  origin: string | null;
  return_date: string | null;
  quote_round: number;
  client_note: string | null;
  options: TicketOption[];
  /** Which request to work on first (0-100) and why. */
  urgency: { score?: number; reasons?: string[] };
  /** Only on one request (empty in lists). */
  request_files: RequestFile[];
  booking_steps: { key: string; label_en: string; label_ar: string; done: boolean; at: string | null; by: string | null }[];
  documents_sent_at: string | null;
  notice: string | null;
  /** Pipeline stage and money (every request); payments, client documents and trip plan (one request). */
  stage: Stage;
  money: TicketMoney;
  last_client_at: string | null;
  cost_price: number | null;
  payment_list: TicketPayment[];
  client_documents: { items: ClientDoc[]; unsorted: number[]; missing: number };
  itinerary: PlanDay[] | null;
  /** The step the request is at (every request) and its whole process (one request). */
  current_step: Pick<WorkflowStep, "key" | "type" | "label_en" | "label_ar" | "started_at"> | null;
  process?: Process | null;
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
  /** Members community levels for the Community section (when switched on). */
  members?: PublicMemberLevel[] | null;
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

// --- Instagram Direct connection --------------------------------------------------------------

export type InstagramConnectionStatus = "connected" | "not_connected" | "needs_token" | "needs_app_secret";

export interface InstagramStatus {
  status: InstagramConnectionStatus;
  account_id: string | null;
  username: string | null;
  token_set: boolean;
  app_secret_set: boolean;
  webhook_path: string | null;
  verify_token: string | null;
}

export interface InstagramTestResult {
  result: "connected" | "token_invalid" | "account_mismatch" | "account_missing" | "no_access" | "network" | "not_configured";
  message: string;
  user_id: string | null;
  username: string | null;
  status: InstagramStatus;
}

// --- Business tools: Customers, activity log, System health ------------------------------------

export interface CustomerRow {
  id: number;
  member_level?: MemberLevel | null;
  name: string | null;
  phone: string | null;
  email: string | null;
  channels: string[];
  first_contact: string | null;
  last_contact: string | null;
  conversations: number;
  bookings: number;
  total_booked: number;
  total_paid: number;
  tags: string[];
}

export interface CustomerList {
  customers: CustomerRow[];
  total: number;
  currency: string;
}

export interface CustomerDetail extends CustomerRow {
  notes: string;
  whatsapp_id: string | null;
  instagram: boolean;
  created_at: string;
  conversation_list: { id: number; channel: string; status: string; created_at: string; last_message_at: string }[];
  ticket_list: {
    id: number; reference: string; package_title: string; departure_date: string | null; status: string;
    total_price: number; currency: string; created_at: string;
  }[];
  can_see_tickets: boolean;
  currency: string;
}

export interface ActivityItem {
  id: number;
  created_at: string;
  user_id: number | null;
  actor: string;
  action: string;
  label: string;
  target: string | null;
  detail: string | null;
}

export interface ActivityPage {
  items: ActivityItem[];
  actions: Record<string, string>;
  people: { user_id: number | null; actor: string }[];
  has_more: boolean;
}

export interface ChannelActivity {
  channel: "whatsapp" | "instagram";
  incoming_24h: number;
  replies_24h: number;
  failed_24h: number;
  last_incoming_at: string | null;
  companies_connected: number;
}

export interface SystemHealth {
  version: string;
  release: string;
  environment: string;
  started_at: string;
  server_time: string;
  database: { ok: boolean; latency_ms: number; dialect: string | null; error: string | null };
  channels: ChannelActivity[];
  errors_24h: { server: number; client: number };
}

export interface ErrorEventRow {
  id: number;
  created_at: string;
  last_seen_at: string;
  source: "server" | "client";
  method: string | null;
  path: string | null;
  page: string | null;
  status: number | null;
  error_type: string | null;
  message: string | null;
  user_id: number | null;
  company_id: number | null;
  company_name: string | null;
  release: string | null;
  count: number;
}

// --- Business trip requests (B2B) ---
export type TripStatus = "new" | "with_vendor" | "options_ready" | "with_client" | "chosen" | "approved" | "booked"
  | "completed" | "cancelled";
export type TripPart = "flight" | "hotel" | "transport" | "activity" | "food";

export interface TripMessage { id: number; thread: "client" | "vendor"; author_kind: string; author_name: string | null; text: string; created_at: string }
export interface TripStep { action: string; created_at: string }

interface TripCommon {
  id: number;
  reference: string;
  status: TripStatus;
  purpose: string | null;
  origin: string | null;
  destination: string;
  depart_date: string | null;
  return_date: string | null;
  travellers: number;
  needs: TripPart[];
  created_at: string;
  updated_at: string;
  currency: string;
}

/** Money comes from the server as text ("480.000"). */
export type Amount = string | number | null;

export interface StaffTripOption {
  id: number; category: TripPart; title: string; provider: string | null; details: string | null;
  cost_price: Amount; price: Amount; added_by: "vendor" | "staff" | "ai"; sent_to_client: boolean; chosen: boolean;
  /** The AI planner's estimate and reason (staff only). */
  estimate_price?: Amount; ai_reason?: string | null;
}

export interface StaffTrip extends TripCommon {
  source: string;
  client_id: number | null;
  client_name: string;
  vendor_id: number | null;
  vendor_name: string | null;
  vendor_accepted: boolean | null;
  traveller_names: string | null;
  budget: string | null;
  notes: string | null;
  vendor_brief: string | null;
  markup_percent: Amount;
  booking_reference: string | null;
  booking_notes: string | null;
  total_price: Amount;
  total_cost: Amount;
  options: StaffTripOption[];
  events: (TripStep & { actor_kind: string; actor_name: string | null; detail: string | null })[];
  messages: TripMessage[];
}

export interface StaffTripRow {
  id: number; reference: string; status: TripStatus; source: string; client_name: string; vendor_name: string | null;
  destination: string; depart_date: string | null; travellers: number; updated_at: string;
}

export interface ClientTrip extends TripCommon {
  traveller_names: string | null;
  budget: string | null;
  notes: string | null;
  booking_reference: string | null;
  total_price: Amount;
  options: { id: number; category: TripPart; title: string; provider: string | null; details: string | null; price: Amount; chosen: boolean }[];
  steps: TripStep[];
  messages: TripMessage[];
}

export interface VendorTrip extends TripCommon {
  brief: string | null;
  traveller_names: string | null;
  accepted: boolean | null;
  booking_reference: string | null;
  booking_notes: string | null;
  total_cost: Amount;
  options: { id: number; category: TripPart; title: string; provider: string | null; details: string | null; cost_price: Amount; chosen: boolean }[];
  steps: TripStep[];
  messages: TripMessage[];
}
