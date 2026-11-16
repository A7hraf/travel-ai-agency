/** Arabic texts of the second big round: features and AI controls, workflows, the AI as the middle layer, team
 *  tools, reminders, broadcasts and B2B. English text is the key. (ar.ts merges AR_V2 into AR.) */
export const AR_V2: Record<string, string> = {
  // Features and AI
  "Features and AI": "الميزات والذكاء الاصطناعي",
  "Give this company features and AI capabilities. Limit the uses per month or in total, the number of employees who may use each one (its admin picks them), and set a monthly price.":
    "امنح هذه الشركة الميزات وقدرات الذكاء الاصطناعي. حدّد عدد الاستخدامات شهرياً أو إجمالاً، وعدد الموظفين المسموح لهم (يختارهم مدير الشركة)، والسعر الشهري.",
  "AI capabilities": "قدرات الذكاء الاصطناعي",
  "Used: {n}": "المستخدم: {n}",
  "Limit": "الحد",
  "No limit": "بلا حد",
  "per month": "شهرياً",
  "in total": "إجمالاً",
  "this month": "هذا الشهر",
  "Employees": "الموظفون",
  "All staff": "كل الموظفين",
  "Price per month": "السعر الشهري",
  "Analytics shown": "التحليلات المعروضة",
  "Add-ons: {v} per month": "الإضافات: {v} شهرياً",
  "No extra features yet. Ask the platform owner to open the ones you need.": "لا توجد ميزات إضافية بعد. اطلب من مالك المنصة فتح ما تحتاجه.",
  "{used} of {limit} {period}": "{used} من {limit} {period}",
  "{used} uses": "{used} استخدام",
  "Who uses it ({n} of {max})": "من يستخدمها ({n} من {max})",
  "Basic figures": "أرقام أساسية",
  "Marketing data": "بيانات التسويق",
  "Deep analysis": "تحليل معمّق",
  "Finance": "المالية",
  "Broadcasts and custom feedback to groups of clients": "الرسائل الجماعية والاستبيانات المخصصة لمجموعات العملاء",
  "AI day-by-day trip plans": "برامج الرحلات اليومية بالذكاء الاصطناعي",
  "AI writes the messages and quotation details the team sends to clients": "يكتب الذكاء الاصطناعي الرسائل وتفاصيل العروض التي يرسلها الفريق للعملاء",
  "AI builds services and their process from the owner's description": "يبني الذكاء الاصطناعي الخدمات ومراحلها من وصف المالك",
  "AI creates packages and experiences": "ينشئ الذكاء الاصطناعي الباقات والتجارب",
  "AI work plan for each employee: today, this week, this month": "خطة عمل بالذكاء الاصطناعي لكل موظف: اليوم، هذا الأسبوع، هذا الشهر",
  "Your company admin has not given you this feature": "لم يمنحك مدير شركتك هذه الميزة",
  "Only travel company staff have company features": "ميزات الشركة لموظفي شركة السفر فقط",
  "This feature is not given per employee": "هذه الميزة لا تُمنح لكل موظف",
};

export const AR_V2_PATTERNS: [RegExp, string][] = [
  [/^Your company used all (\d+) uses of this feature this month$/, "استخدمت شركتك كل الاستخدامات ({1}) لهذه الميزة هذا الشهر"],
  [/^Your company used all (\d+) uses of this feature in total$/, "استخدمت شركتك كل الاستخدامات ({1}) لهذه الميزة"],
  [/^All (\d+) places for this feature are taken$/, "كل الأماكن ({1}) لهذه الميزة مشغولة"],
  [/^Unknown feature: (.+)$/, "ميزة غير معروفة: {1}"],
];
