import type { Lang } from "../Money";
import type { StorefrontText } from "../../i18n";
import type { PublicCompany, TravelPackage } from "../../types";
import type { ChatEngine } from "./useChat";

/** Page parts in display order: trips (featured / offers), "How booking works", about & contact. */
export type Block = "featured" | "offers" | "how" | "about";

/** Everything the phone and desktop layouts share. */
export interface StoreCtx {
  slug: string;
  company: PublicCompany;
  packages: TravelPackage[];
  t: StorefrontText;
  lang: Lang;
  toggleLang: () => void;
  chat: ChatEngine;
  agent: string;
  whatsapp: string | null;
  // search
  query: string;
  setQuery: (v: string) => void;
  budget: string;
  setBudget: (v: string) => void;
  cat: number;
  setCat: (v: number) => void;
  cats: number[];
  shown: TravelPackage[];
  featured: TravelPackage[];
  filtering: boolean;
  clearFilters: () => void;
  // page content
  blocks: Block[];
  heroTitle: string | null;
  heroText: string | null;
  about: { title: string; text: string } | null;
  showContact: boolean;
  // actions
  openPackage: (p: TravelPackage) => void;
  book: (p: TravelPackage) => void;
  openChat: () => void;
  askNew: () => void;
}
