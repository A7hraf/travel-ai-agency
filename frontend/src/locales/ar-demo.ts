/** Arabic texts of the platform owner's "Create demo company" (Companies page). English text is the key. */
export const AR_DEMO: Record<string, string> = {
  "Create demo company": "إنشاء شركة تجريبية",
  "A ready-made travel agency in Muscat to present the system: 12 packages, 4 staff logins, trained answers, a designed customer page and, if you like, a month of sample chats and bookings. Sample customers are fictional and no WhatsApp message is sent.":
    "وكالة سفر جاهزة في مسقط لعرض النظام: 12 باقة، 4 حسابات موظفين، إجابات مدرَّبة، صفحة عملاء مصمَّمة، ومحادثات وحجوزات تجريبية لشهر كامل إن أردت. العملاء التجريبيون وهميون ولا تُرسل أي رسالة واتساب.",
  "Package texts": "لغة نصوص الباقات",
  "English and Arabic": "الإنجليزية والعربية",
  "English": "الإنجليزية",
  "Arabic": "العربية",
  "Admin login email (optional)": "بريد دخول المدير (اختياري)",
  "Empty: admin@{address}.example": "إذا تُرك فارغاً: admin@{address}.example",
  "Include sample activity": "إضافة نشاط تجريبي",
  "30 days of web and WhatsApp chats and bookings in every status, so the dashboard, inbox and tickets look alive.":
    "محادثات موقع وواتساب وحجوزات بكل الحالات خلال 30 يوماً، لتظهر لوحة التحكم والمحادثات والتذاكر حيّة.",
  "Demo company ready": "الشركة التجريبية جاهزة",
  "Save these logins now. The passwords are shown only once and can't be shown again (you can set new ones on the company page).":
    "احفظ بيانات الدخول الآن. كلمات المرور تظهر مرة واحدة فقط ولا يمكن عرضها مجدداً (يمكنك تعيين كلمات جديدة من صفحة الشركة).",
  "Close? The passwords will not be shown again.": "إغلاق؟ لن تظهر كلمات المرور مرة أخرى.",
  "{n} conversations": "{n} محادثة",
  "{n} tickets": "{n} تذكرة",
  "All logins": "كل بيانات الدخول",
  "I saved the logins": "حفظت بيانات الدخول",
  "Login page": "صفحة الدخول",
  "Done": "تم",

  // Server messages
  "You can create 3 demo companies per hour. Please try again later.":
    "يمكنك إنشاء 3 شركات تجريبية في الساعة. حاول مرة أخرى لاحقاً.",
  "Enter the company name": "أدخل اسم الشركة",
};

/** Server texts with numbers or dates in them (lead merges into AR_PATTERNS). */
export const AR_DEMO_PATTERNS: [RegExp, string][] = [
  [/^(\d+) seats are already booked on (\S+)\. Set at least (\d+) seats per date, or cancel bookings first\.$/,
    "تم حجز {1} مقعد بتاريخ {2}. اجعل المقاعد لكل تاريخ {3} على الأقل، أو ألغِ بعض الحجوزات أولاً."],
];
