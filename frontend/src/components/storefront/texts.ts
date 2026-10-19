/** Customer-page texts the agency can replace on the page editor (Texts tab).
 *  The keys match TEXT_KEYS in backend/app/branding.py. Texts made from a template may use
 *  {agent} (the AI consultant's name) and {company}. */
import { STOREFRONT_TEXT, type StorefrontText } from "../../i18n";
import type { Lang } from "../Money";
import type { PageTexts } from "../../types";

export interface TextField {
  key: string;
  /** English label for the editor (translated with t()). */
  label: string;
  long?: boolean;
  max: number;
  /** Placeholders the text may use. */
  vars?: ("agent" | "company")[];
}

export interface TextGroup { id: string; title: string; fields: TextField[] }

const S = 80, M = 200, L = 600;
const f = (key: string, label: string, max = S, extra: Partial<TextField> = {}): TextField => ({ key, label, max, ...extra });
const A: Partial<TextField> = { vars: ["agent"] };

export const TEXT_GROUPS: TextGroup[] = [
  { id: "hero", title: "Top banner and search", fields: [
    f("online", "Small line above the title (phone)", S, A),
    f("fromOman", "Small line above the title (computer)"),
    f("heroA", "Title"),
    f("heroB", "Highlighted word of the title"),
    f("searchPlaceholder", "Search box hint (phone)"),
    f("webSearchPlaceholder", "Search box hint (computer)"),
    f("budgetPlaceholder", "Budget box hint (phone)"),
    f("webBudgetPlaceholder", "Budget box hint (computer)"),
    f("findTrips", "Search button"),
    f("trust1", "Trust point 1"),
    f("trust2", "Trust point 2"),
    f("trust3", "Trust point 3"),
  ] },
  { id: "nav", title: "Top bar", fields: [
    f("navTrips", "Link: trips"),
    f("navHow", "Link: how it works"),
    f("navAbout", "Link: about"),
    f("switchTo", "Language button"),
    f("whatsapp", "WhatsApp button"),
  ] },
  { id: "trips", title: "Trips", fields: [
    f("featuredTitle", "Featured trips title"),
    f("offers", "Offers title (phone)"),
    f("tripsOnSale", "Trips title (computer)"),
    f("cat0", "Trip type: All"),
    f("cat1", "Trip type: Honeymoon"),
    f("cat2", "Trip type: Family"),
    f("cat3", "Trip type: Beach"),
    f("cat4", "Trip type: City"),
    f("cat5", "Trip type: Umrah"),
    f("pricesNote", "Note under the prices", M),
    f("perPerson", "\"per person\" label"),
    f("perAdult", "\"per adult\" label"),
    f("perChild", "\"per child\" label"),
    f("from", "\"From\" before a price"),
    f("noMatch", "No trip matches the search", M),
    f("askCustom", "Button: ask for a custom trip", S, A),
    f("clear", "Button: clear the search"),
    f("comingSoon", "No trips yet", M),
    f("askNow", "Button when there are no trips", S, A),
  ] },
  { id: "buttons", title: "Booking buttons", fields: [
    f("book", "Book button (phone list)"),
    f("bookWith", "Book button (cards and trip details)", S, A),
    f("bookThis", "Book button (trip suggested in the chat)"),
    f("viewTrip", "View trip button (chat)"),
  ] },
  { id: "details", title: "Trip details", fields: [
    f("included", "Included title"),
    f("notIncluded", "Not included title"),
    f("departures", "Departure dates title"),
    f("flexible", "No fixed dates"),
    f("soldOut", "Sold out"),
  ] },
  { id: "how", title: "How booking works", fields: [
    f("howKicker", "Small title"),
    f("howTitle", "Title, first part", M, A),
    f("howAccent", "Title, highlighted part"),
    f("howEnd", "Title, last part", M),
    f("how1Title", "Step 1 title", S, A),
    f("how1Text", "Step 1 text", L, { ...A, long: true }),
    f("how2Title", "Step 2 title", S, A),
    f("how2Text", "Step 2 text", L, { ...A, long: true }),
    f("how3Title", "Step 3 title", S, A),
    f("how3Text", "Step 3 text", L, { ...A, long: true }),
  ] },
  { id: "about", title: "About us and contact", fields: [
    f("aboutQuote", "Quote next to the about text", M),
    f("contactTitle", "Contact title (when there is no about text)"),
    f("contactText", "Contact text (when there is no about text)", L, { long: true }),
  ] },
  { id: "footer", title: "Footer", fields: [
    f("footer", "Footer sentence", M),
  ] },
  { id: "chat", title: "Chat", fields: [
    f("chatWith", "Chat button", S, A),
    f("chatButtonSub", "Line under the chat button (phone)"),
    f("aiSub", "Line under the consultant's name"),
    f("humanSub", "Line when a person has taken over"),
    f("consultant", "Name shown for your team"),
    f("live", "\"Live\" label"),
    f("welcome", "Welcome message", L, { vars: ["agent", "company"], long: true }),
    f("qHoney", "Quick reply 1"),
    f("qFamily", "Quick reply 2"),
    f("qHuman", "Quick reply 3"),
    f("typeHere", "Message box hint"),
    f("askAnything", "Message box hint (computer)", S, A),
    f("newChat", "New conversation"),
    f("newChatQ", "New conversation question", M),
    f("cancel", "Cancel"),
    f("start", "Start new"),
    f("retry", "Try again"),
    f("tooFast", "Too many messages", M),
    f("notSent", "Message not sent", M),
  ] },
  { id: "booking", title: "Booking summary in the chat", fields: [
    f("summary", "Summary title"),
    f("sPkg", "Package"),
    f("sDate", "Departure"),
    f("sPax", "Travellers"),
    f("sTotal", "Total"),
    f("confirmBooking", "Confirm button"),
    f("change", "Change button"),
    f("yesConfirm", "Message sent by Confirm", M),
    f("changeMsg", "Message sent by Change", M),
    f("booked", "Booking received"),
    f("bookedRef", "Your reference"),
  ] },
];

export const TEXT_FIELDS: Record<string, TextField> = Object.fromEntries(
  TEXT_GROUPS.flatMap((g) => g.fields.map((x) => [x.key, x])),
);

const fill = (text: string, agent: string, company = "") => text.split("{agent}").join(agent).split("{company}").join(company);

/** The standard text of a field, with the names filled in (shown as the placeholder). */
export function defaultText(lang: Lang, key: string, agent: string, company: string, whatsapp: boolean): string {
  const t = STOREFRONT_TEXT[lang] as unknown as Record<string, unknown>;
  let m = key.match(/^trust(\d)$/);
  if (m) return STOREFRONT_TEXT[lang].trust[Number(m[1]) - 1] ?? "";
  m = key.match(/^cat(\d)$/);
  if (m) return STOREFRONT_TEXT[lang].categories[Number(m[1])] ?? "";
  m = key.match(/^how(\d)(Title|Text)$/);
  if (m) {
    const step = STOREFRONT_TEXT[lang].how(agent, whatsapp)[Number(m[1]) - 1];
    return m[2] === "Title" ? step.title : step.text;
  }
  const v = t[key];
  if (typeof v === "string") return v;
  if (typeof v === "function") return key === "welcome" ? (v as (a: string, c: string) => string)(agent, company) : (v as (a: string) => string)(agent);
  return "";
}

/** The page texts with the agency's own texts in place of the standard ones. */
export function applyTexts(lang: Lang, texts: PageTexts | undefined): StorefrontText {
  const base = STOREFRONT_TEXT[lang];
  const own = texts?.[lang] ?? {};
  const keys = Object.keys(own).filter((k) => TEXT_FIELDS[k] && own[k]?.trim());
  if (!keys.length) return base;
  const out = { ...base } as Record<string, unknown>;
  const trust = [...base.trust];
  const cats = [...base.categories];
  const steps: Record<string, string> = {};
  for (const key of keys) {
    const text = own[key].trim();
    let m = key.match(/^trust(\d)$/);
    if (m) { trust[Number(m[1]) - 1] = text; continue; }
    m = key.match(/^cat(\d)$/);
    if (m) { cats[Number(m[1])] = text; continue; }
    if (/^how\d(Title|Text)$/.test(key)) { steps[key] = text; continue; }
    const standard = (base as unknown as Record<string, unknown>)[key];
    if (typeof standard === "function") {
      out[key] = key === "welcome" ? (agent: string, company: string) => fill(text, agent, company) : (agent: string) => fill(text, agent);
    } else {
      out[key] = text;
    }
  }
  out.trust = trust;
  out.categories = cats;
  if (Object.keys(steps).length) {
    out.how = (agent: string, whatsapp: boolean) => base.how(agent, whatsapp).map((s, i) => ({
      title: steps[`how${i + 1}Title`] ? fill(steps[`how${i + 1}Title`], agent) : s.title,
      text: steps[`how${i + 1}Text`] ? fill(steps[`how${i + 1}Text`], agent) : s.text,
    }));
  }
  return out as unknown as StorefrontText;
}
