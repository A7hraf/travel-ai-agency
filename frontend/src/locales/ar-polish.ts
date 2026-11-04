/** Arabic texts added in the loading-state and Arabic polish pass. English text is the key. */
export const AR_POLISH: Record<string, string> = {
  // Loading states (a sleeping server can take up to a minute to answer)
  "Still loading — the server may be waking up. This can take up to a minute.":
    "ما زال التحميل جارياً، فقد يكون الخادم في طور التشغيل. قد يستغرق ذلك حتى دقيقة.",
  "Loading the invoice…": "جارٍ تحميل الفاتورة…",
  "Customer details": "بيانات العميل",
  "Departs": "إقلاع",
};

/** Server texts with names or numbers in them (page-design validation, demo company). */
export const AR_POLISH_PATTERNS: [RegExp, string][] = [
  [/^texts must be an object with 'en' and 'ar'$/, "يجب أن تحتوي النصوص على العربية والإنجليزية"],
  [/^unknown language '(.+)' in texts$/, "لغة غير معروفة في النصوص: {1}"],
  [/^texts of a language must be an object$/, "نصوص اللغة غير صالحة"],
  [/^'(.+)' is not an editable text$/, "النص «{1}» لا يمكن تعديله"],
  [/^text '(.+)' must be a string$/, "النص «{1}» يجب أن يكون نصاً"],
  [/^text '(.+)' is too long \(maximum (\d+) characters\)$/, "النص «{1}» طويل جداً (الحد الأقصى {2} حرف)"],
  [/^language must be one of (.+)$/, "اللغة يجب أن تكون إحدى: {1}"],
];

/** Counted nouns: Arabic uses singular, dual, plural (3–10) and singular again (11+). Keyed by the English text. */
export const AR_POLISH_PLURALS: Record<string, { zero?: string; one: string; two: string; few: string; many: string; other: string }> = {
  "{n} chats": { zero: "لا محادثات", one: "محادثة واحدة", two: "محادثتان", few: "{n} محادثات", many: "{n} محادثة", other: "{n} محادثة" },
  "{n} conversations": { zero: "لا محادثات", one: "محادثة واحدة", two: "محادثتان", few: "{n} محادثات", many: "{n} محادثة", other: "{n} محادثة" },
  "{n} answers": { zero: "لا إجابات", one: "إجابة واحدة", two: "إجابتان", few: "{n} إجابات", many: "{n} إجابة", other: "{n} إجابة" },
  "{n} packages": { zero: "لا باقات", one: "باقة واحدة", two: "باقتان", few: "{n} باقات", many: "{n} باقة", other: "{n} باقة" },
  "{n} open tickets": { zero: "لا تذاكر مفتوحة", one: "تذكرة مفتوحة واحدة", two: "تذكرتان مفتوحتان", few: "{n} تذاكر مفتوحة", many: "{n} تذكرة مفتوحة", other: "{n} تذكرة مفتوحة" },
  "{n} booking tickets": { zero: "لا تذاكر حجز", one: "تذكرة حجز واحدة", two: "تذكرتا حجز", few: "{n} تذاكر حجز", many: "{n} تذكرة حجز", other: "{n} تذكرة حجز" },
  "{n} tickets": { zero: "لا تذاكر", one: "تذكرة واحدة", two: "تذكرتان", few: "{n} تذاكر", many: "{n} تذكرة", other: "{n} تذكرة" },
  "{n} bookings": { zero: "لا حجوزات", one: "حجز واحد", two: "حجزان", few: "{n} حجوزات", many: "{n} حجزاً", other: "{n} حجز" },
  "{n} customers": { zero: "لا عملاء", one: "عميل واحد", two: "عميلان", few: "{n} عملاء", many: "{n} عميلاً", other: "{n} عميل" },
  "{n} companies": { zero: "لا شركات", one: "شركة واحدة", two: "شركتان", few: "{n} شركات", many: "{n} شركة", other: "{n} شركة" },
  "{n} days left": { zero: "لم يتبقَّ أي يوم", one: "متبقٍ يوم واحد", two: "متبقٍ يومان", few: "متبقٍ {n} أيام", many: "متبقٍ {n} يوماً", other: "متبقٍ {n} يوم" },
  "{n} seats left": { zero: "لا مقاعد متبقية", one: "مقعد واحد متبقٍ", two: "مقعدان متبقيان", few: "{n} مقاعد متبقية", many: "{n} مقعداً متبقياً", other: "{n} مقعد متبقٍ" },
  "{n} permissions": { zero: "بلا صلاحيات", one: "صلاحية واحدة", two: "صلاحيتان", few: "{n} صلاحيات", many: "{n} صلاحية", other: "{n} صلاحية" },
  "{n} new answers": { zero: "لا إجابات جديدة", one: "إجابة جديدة واحدة", two: "إجابتان جديدتان", few: "{n} إجابات جديدة", many: "{n} إجابة جديدة", other: "{n} إجابة جديدة" },
};
