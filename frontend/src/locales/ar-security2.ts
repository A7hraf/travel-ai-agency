/** Arabic texts for the messages added by the second security review. English text is the key
 *  (server messages are translated by trServer). To merge: Object.assign(AR, ..., AR_SECURITY2) and
 *  AR_PATTERNS.push(...AR_SECURITY2_PATTERNS) in locales/ar.ts. */
export const AR_SECURITY2: Record<string, string> = {
  // Platform settings: the API key only goes to the server it was set up with
  "Enter the API key for this AI server: a key is only sent to the server it was set up with":
    "أدخل مفتاح API لخادم الذكاء الاصطناعي هذا: لا يُرسَل المفتاح إلا إلى الخادم الذي أُعدّ له",
  // Platform settings: cloud metadata addresses
  "This server address is not allowed": "عنوان الخادم هذا غير مسموح به",
  "This AI server address is not allowed (cloud metadata address)":
    "عنوان خادم الذكاء الاصطناعي هذا غير مسموح به (عنوان بيانات وصفية سحابية)",
  // My account: too many wrong current passwords
  "Too many wrong passwords, try again in 15 minutes": "محاولات كثيرة بكلمة مرور خاطئة، حاول مرة أخرى بعد 15 دقيقة",
  // Settings > Test AI for a company (when the company.py patch is applied)
  "The AI is not working right now. Please tell the platform owner: the details are on the platform console.":
    "الذكاء الاصطناعي لا يعمل الآن. يرجى إبلاغ مالك المنصة: التفاصيل في لوحة تحكم المنصة.",
  // AI training (when the ai/training.py patch is applied)
  "The test chat was used a lot this hour. Please try again later.":
    "استُخدمت محادثة التجربة كثيراً خلال هذه الساعة. يرجى المحاولة لاحقاً.",
  "The text could not be read. Put one answer on each line: question | answer":
    "تعذّرت قراءة النص. ضع إجابة واحدة في كل سطر: السؤال | الإجابة",
};

/** Server texts with a model name or an error in them: English pattern -> Arabic template. */
export const AR_SECURITY2_PATTERNS: [RegExp, string][] = [
  [/^(\S+) -> cannot reach the AI server: (.*)$/, "{1} ← تعذّر الوصول إلى خادم الذكاء الاصطناعي: {2}"],
];
