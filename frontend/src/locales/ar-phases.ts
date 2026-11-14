/** Arabic texts of the supplier library, branded quotations, reports, calendar and the AI advisor.
 *  English text is the key. (ar.ts merges AR_PHASES into AR.) */
export const AR_PHASES: Record<string, string> = {
  // Features the platform owner switches on
  "Supplier library: saved hotels, airlines, transport and activities, suggested again for similar requests":
    "مكتبة الموردين: فنادق وشركات طيران ونقل وأنشطة محفوظة، تُقترح مجدداً للطلبات المشابهة",
  "Branded quotations: draft and final quotations as printable PDF pages with photos":
    "عروض أسعار بهوية الشركة: عروض أولية ونهائية كصفحات PDF قابلة للطباعة مع الصور",
  "Reports: business reports as branded PDF pages": "التقارير: تقارير الأعمال كصفحات PDF بهوية الشركة",
  "Calendar and reminders: appointments, airport meetings and reminders on WhatsApp":
    "التقويم والتذكيرات: المواعيد واستقبال المطار والتذكير على واتساب",
  "AI advisor: a chat with the AI about the business, with its recommendations": "المستشار الذكي: محادثة مع الذكاء الاصطناعي عن العمل وتوصياته",
  "Spending figures: how much is spent with each supplier, what clients book most":
    "أرقام الإنفاق: كم يُنفق مع كل مورد، وما يحجزه العملاء أكثر",
  "Margin learning: suggests the client price from the company's usual margin": "تعلّم هامش الربح: يقترح سعر العميل من هامش الشركة المعتاد",
  "Excel downloads of the reports": "تنزيل التقارير بصيغة Excel",
  "Reminders to clients on WhatsApp": "تذكير العملاء على واتساب",
  "AI trip planner: drafts up to 3 choices per part (with web search) and learns from your team":
    "مخطط الرحلات الذكي: يقترح حتى 3 خيارات لكل جزء (مع البحث في الإنترنت) ويتعلم من فريقك",
  "This feature is not switched on for your company": "هذه الميزة غير مفعّلة لشركتك",

  // Supplier library
  "Supplier library": "مكتبة الموردين",
  "The hotels, airlines, transport and activities you work with. Saved once, suggested again for requests to the same place, and counted in your spending.":
    "الفنادق وشركات الطيران والنقل والأنشطة التي تعمل معها. تُحفظ مرة، وتُقترح مجدداً لطلبات المكان نفسه، وتُحسب في إنفاقك.",
  "Add a supplier": "أضف مورداً",
  "Name or place": "الاسم أو المكان",
  "Nothing saved yet. Add suppliers here, or save a choice from a request with the bookmark button.":
    "لا شيء محفوظ بعد. أضف الموردين هنا، أو احفظ خياراً من طلب بزر الحفظ.",
  "anywhere": "أي مكان",
  "chosen {n} times": "اختير {n} مرة",
  "City or country": "المدينة أو الدولة",
  "Empty: suggested for any place (airlines, insurance…)": "فارغ: يُقترح لأي مكان (الطيران، التأمين…)",
  "Your usual cost": "تكلفتك المعتادة",
  "Usual client price": "سعر العميل المعتاد",
  "Description for clients (shown in quotations)": "وصف للعملاء (يظهر في عروض الأسعار)",
  "Notes for your team (contacts, contract rates…)": "ملاحظات لفريقك (جهات الاتصال، أسعار العقود…)",
  "Photo (your own or the supplier's official photo)": "صورة (صورتك أو الصورة الرسمية للمورد)",
  "Preferred": "مفضّل",
  "Suggested first for requests to this place.": "يُقترح أولاً لطلبات هذا المكان.",
  "In use": "مستخدم",
  "Spending and margins (last 12 months, paid requests)": "الإنفاق والهوامش (آخر 12 شهراً، الطلبات المدفوعة)",
  "{n} bookings · margin {v}": "{n} حجز · الهامش {v}",
  "No paid requests yet: the figures appear after the first payments.": "لا توجد طلبات مدفوعة بعد: تظهر الأرقام بعد أول المدفوعات.",
  "Supplier": "المورد",
  "You paid": "دفعتَ",
  "Clients paid": "دفع العملاء",
  "not saved": "غير محفوظ",
  "Hotels booked by stars:": "الفنادق المحجوزة حسب النجوم:",
  "Your usual margin:": "هامشك المعتاد:",
  "Use your usual margin ({p}%): {v}": "استخدم هامشك المعتاد ({p}%): {v}",
  "Photo for the quotation (optional)": "صورة لعرض السعر (اختياري)",
  "Save to the library": "احفظ في المكتبة",
  "From your library:": "من مكتبتك:",
  "{who} saved {new} to the library": "حفظ {who} {new} في المكتبة",
  "Supplier not found": "المورد غير موجود",
  "The library is full": "المكتبة ممتلئة",
  "Upload the photo (photos from other websites can't be used)": "ارفع الصورة (لا يمكن استخدام صور من مواقع أخرى)",
};

export const AR_PHASES_PATTERNS: [RegExp, string][] = [];
