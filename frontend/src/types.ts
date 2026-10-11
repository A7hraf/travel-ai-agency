export type Role = "system_admin" | "company_admin" | "support" | "ticket_agent";

export interface CompanyBrief {
  id: number;
  name: string;
  slug: string;
  status: string;
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
  ai_instructions: string;
  knowledge_base: string;
  whatsapp_phone_number_id: string | null;
  whatsapp_display_number: string | null;
  whatsapp_token_set: boolean;
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
}

export interface Dashboard {
  conversations_by_status: Record<string, number>;
  tickets_by_status: Record<string, number>;
  pipeline_value: number;
  confirmed_value: number;
  currency: string;
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
}

export interface PublicMessage {
  id: number;
  sender: "customer" | "ai" | "agent";
  content: string;
  created_at: string;
}
