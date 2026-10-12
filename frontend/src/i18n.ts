import { useEffect, useState } from "react";
import type { Lang } from "./components/Money";

const STORAGE_KEY = "travel_lang";

/** Texts of the customer page and chat, in English and Arabic. */
export const STOREFRONT_TEXT = {
  en: {
    switchTo: "العربية",
    heroTitle: "Where do you want to go next?",
    heroText: (agent: string) =>
      `Browse our packages or chat with ${agent}, our AI travel consultant. Available 24/7, in Arabic and English.`,
    searchPlaceholder: "Destination, country or trip type (beach, honeymoon, family…)",
    budgetPlaceholder: "Max budget per person",
    chatWith: (agent: string) => `Chat with ${agent}`,
    whatsapp: "WhatsApp us",
    offers: "Our offers",
    noMatch: "No package matches your search.",
    askFor: (agent: string) => `Ask ${agent}`,
    customTrip: "for a custom trip.",
    days: (n: number) => `${n} days`,
    starHotel: "hotel",
    perPerson: "/ person",
    perAdult: "per adult",
    perChild: "per child",
    book: "Book",
    bookWith: (agent: string) => `Book with ${agent}`,
    featured: "★ Featured",
    included: "Included",
    notIncluded: "Not included",
    hotel: "Hotel",
    departures: "Departures",
    flexible: "Flexible, on request",
    price: "Price",
    seatsLeft: "Seats left",
    pricesNote: "Prices in Omani rials (OMR) per person.",
    footer: "Payments are handled by our team, never by the chat.",
    interested: (title: string, days: number) =>
      `Hi! I'm interested in the "${title}" package (${days} days). Can you tell me more?`,
    aiSub: "AI travel consultant · replies instantly",
    humanSub: "A travel consultant is with you",
    consultant: "Travel consultant",
    newChat: "New conversation",
    close: "Close chat",
    typeHere: "Type your message…",
    send: "Send",
    tooFast: "You're sending messages too fast, please wait a moment.",
    notSent: "Message not sent, please try again.",
    notFound: "This travel agency page does not exist.",
    loading: "Loading…",
  },
  ar: {
    switchTo: "English",
    heroTitle: "وين وجهتك الجاية؟",
    heroText: (agent: string) =>
      `تصفّح باقاتنا أو تحدّث مع ${agent}، مستشارة السفر الذكية. متاحة على مدار الساعة بالعربي والإنجليزي.`,
    searchPlaceholder: "الوجهة أو الدولة أو نوع الرحلة (شاطئ، شهر عسل، عائلية…)",
    budgetPlaceholder: "أقصى ميزانية للشخص",
    chatWith: (agent: string) => `تحدّث مع ${agent}`,
    whatsapp: "راسلنا واتساب",
    offers: "عروضنا",
    noMatch: "لا توجد باقة تطابق بحثك.",
    askFor: (agent: string) => `اسأل ${agent}`,
    customTrip: "عن رحلة مخصّصة.",
    days: (n: number) => `${n} أيام`,
    starHotel: "فندق",
    perPerson: "/ للشخص",
    perAdult: "للبالغ",
    perChild: "للطفل",
    book: "احجز",
    bookWith: (agent: string) => `احجز مع ${agent}`,
    featured: "★ مميّز",
    included: "يشمل",
    notIncluded: "لا يشمل",
    hotel: "الفندق",
    departures: "مواعيد السفر",
    flexible: "مرنة حسب الطلب",
    price: "السعر",
    seatsLeft: "المقاعد المتبقية",
    pricesNote: "الأسعار بالريال العماني للشخص الواحد.",
    footer: "الدفع يتم عن طريق فريقنا فقط، وليس عبر المحادثة.",
    interested: (title: string, days: number) =>
      `مرحباً! مهتم بباقة "${title}" (${days} أيام). ممكن تعطيني تفاصيل أكثر؟`,
    aiSub: "مستشارة سفر ذكية · ترد فوراً",
    humanSub: "معك الآن أحد مستشاري السفر",
    consultant: "مستشار السفر",
    newChat: "محادثة جديدة",
    close: "إغلاق المحادثة",
    typeHere: "اكتب رسالتك…",
    send: "إرسال",
    tooFast: "ترسل الرسائل بسرعة كبيرة، انتظر لحظة من فضلك.",
    notSent: "لم تُرسل الرسالة، حاول مرة أخرى.",
    notFound: "صفحة وكالة السفر هذه غير موجودة.",
    loading: "جارٍ التحميل…",
  },
};

export type StorefrontText = (typeof STOREFRONT_TEXT)["en"];

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "ar" || saved === "en") return saved;
  } catch {
    /* storage unavailable */
  }
  return navigator.language?.toLowerCase().startsWith("ar") ? "ar" : "en";
}

/** The customer's language, remembered on this device; also sets the page direction. */
export function useLang(): [Lang, (lang: Lang) => void] {
  const [lang, setLang] = useState<Lang>(initialLang);
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch {
      /* storage unavailable */
    }
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    return () => {
      document.documentElement.lang = "en";
      document.documentElement.dir = "ltr";
    };
  }, [lang]);
  return [lang, setLang];
}
