/** Arabic texts of the business accounts: clients and vendors (pages/Partners.tsx, pages/PartnerPortal.tsx,
 *  components/b2b/B2BControls.tsx). English text is the key. (ar.ts merges AR_B2B into AR.) */
export const AR_B2B: Record<string, string> = {
  "Business accounts": "حسابات الأعمال",
  "Business account": "حساب أعمال",
  "Business client": "عميل أعمال",
  "Business clients": "عملاء الأعمال",
  "Vendor": "مورّد",
  "Vendors": "المورّدون",
  "Add business client": "إضافة عميل أعمال",
  "Add vendor": "إضافة مورّد",
  "Companies that request travel for their people. Their logins see their own requests and history only.":
    "شركات تطلب السفر لموظفيها. حساباتها ترى طلباتها وسجلها فقط.",
  "Supplier agencies that arrange flights, hotels, transport, food and activities for your trips.":
    "وكالات مورّدة ترتب الطيران والفنادق والمواصلات والطعام والأنشطة لرحلاتكم.",
  "Business clients who request travel, and the vendors who arrange it. You are the link between them.":
    "عملاء أعمال يطلبون السفر، ومورّدون يرتبونه، وأنتم حلقة الوصل بينهم.",
  "Logins per account": "حسابات الدخول لكل حساب",
  "Limit reached. The platform admin can raise it.": "تم بلوغ الحد. يمكن لمدير المنصة رفعه.",
  "None yet.": "لا يوجد بعد.",
  "{n} features": "{n} ميزات",
  "{n} logins": "{n} حسابات دخول",
  "Paused": "موقوف",
  "Contact person": "الشخص المسؤول",
  "WhatsApp numbers of this business": "أرقام واتساب لهذه الشركة",
  "One per line, with the country code. Messages from these numbers are known to come from this business.":
    "رقم في كل سطر مع رمز الدولة. الرسائل من هذه الأرقام تُعرف أنها من هذه الشركة.",
  "Features": "الميزات",
  "Not allowed by the platform admin": "غير مسموح من مدير المنصة",
  "Account active (its logins can sign in)": "الحساب مفعّل (يمكن لحساباته تسجيل الدخول)",
  "Create": "إنشاء",
  "Delete {name}?": "حذف {name}؟",
  "Delete {name}": "حذف {name}",
  "Its logins are deleted too. This can't be undone.": "ستُحذف حسابات الدخول التابعة له أيضاً. لا يمكن التراجع عن هذا.",
  "No logins yet. Add one so this account can sign in.": "لا توجد حسابات دخول بعد. أضف حساباً ليتمكن من تسجيل الدخول.",
  "Add login": "إضافة حساب دخول",
  "Login limit reached for this account. The platform admin can raise it.": "تم بلوغ حد حسابات الدخول لهذا الحساب. يمكن لمدير المنصة رفعه.",
  "Delete the login of {name}?": "حذف حساب الدخول الخاص بـ {name}؟",
  "Save this password now: it is shown only once.": "احفظ كلمة المرور الآن: تظهر مرة واحدة فقط.",
  "Send it to the person privately. They sign in on the normal login page.": "أرسلها للشخص بشكل خاص. يسجّل الدخول من صفحة الدخول العادية.",
  // Owner controls
  "Let this travel company open accounts for business clients (who request travel) and vendors (who arrange it). You decide how many and which features it can give them.":
    "اسمح لوكالة السفر هذه بفتح حسابات لعملاء الأعمال (الذين يطلبون السفر) والمورّدين (الذين يرتبونه). أنت تحدد العدد والميزات التي يمكنها منحها لهم.",
  "Business accounts switched on": "حسابات الأعمال مفعّلة",
  "When off, the company's business accounts can't sign in and the page is hidden from its staff.":
    "عند الإيقاف، لا تستطيع حسابات الأعمال تسجيل الدخول وتُخفى الصفحة عن موظفي الوكالة.",
  "Business clients (maximum)": "عملاء الأعمال (الحد الأقصى)",
  "Vendors (maximum)": "المورّدون (الحد الأقصى)",
  "Logins per account (maximum)": "حسابات الدخول لكل حساب (الحد الأقصى)",
  "{n} in use": "{n} مستخدم",
  "Features the company may give. Taking one back stops it at once for every account of this company.":
    "الميزات التي يمكن للوكالة منحها. سحب أي ميزة يوقفها فوراً لكل حسابات هذه الوكالة.",
  // Features
  "Request trips from the dashboard": "طلب رحلات من لوحة التحكم",
  "Request trips by WhatsApp from linked numbers": "طلب رحلات عبر واتساب من الأرقام المرتبطة",
  "Chat with the AI assistant": "المحادثة مع المساعد الذكي",
  "Travel history": "سجل السفر",
  "Exclusive packages": "باقات حصرية",
  "Spending reports": "تقارير الإنفاق",
  "Receive trip requests": "استقبال طلبات الرحلات",
  "Send options and prices": "إرسال الخيارات والأسعار",
  "Job history": "سجل الأعمال",
  "Manage business clients and vendors, and their logins": "إدارة عملاء الأعمال والمورّدين وحسابات دخولهم",
  // Portal
  "Welcome, {name}. This is your private space with {company}.": "أهلاً {name}. هذه مساحتك الخاصة مع {company}.",
  "Your services": "خدماتك",
  "No services are switched on for your account yet. Contact {company}.": "لا توجد خدمات مفعّلة لحسابك بعد. تواصل مع {company}.",
  "Opening soon": "قريباً",
  "Request by WhatsApp": "الطلب عبر واتساب",
  "Messages from these numbers are recognised as {name}:": "الرسائل من هذه الأرقام تُعرف أنها من {name}:",
  "No WhatsApp number is linked to your account yet.": "لا يوجد رقم واتساب مرتبط بحسابك بعد.",
  "Write to {company} on WhatsApp:": "راسل {company} على واتساب:",
  // Server messages
  "Business accounts are not switched on for your company. Ask the platform admin.":
    "حسابات الأعمال غير مفعّلة لوكالتك. تواصل مع مدير المنصة.",
  "Business accounts are switched off for this travel company": "حسابات الأعمال متوقفة لدى وكالة السفر هذه",
  "Your business account is paused": "حساب الأعمال الخاص بك موقوف",
  "This area is for travel company staff": "هذه المنطقة مخصصة لموظفي وكالة السفر",
  "This area is for business accounts": "هذه المنطقة مخصصة لحسابات الأعمال",
  "Business account not found": "حساب الأعمال غير موجود",
  "Login not found": "حساب الدخول غير موجود",
  "Only business clients can have linked WhatsApp numbers": "فقط عملاء الأعمال يمكن ربط أرقام واتساب بهم",
  "One of these WhatsApp numbers is already linked to another account": "أحد أرقام واتساب هذه مرتبط بحساب آخر",
};

/** Server texts with numbers or names in them (ar.ts merges these into AR_PATTERNS). */
export const AR_B2B_PATTERNS: [RegExp, string][] = [
  [/^Limit reached: (\d+)\/(\d+) client accounts\. Ask the platform admin to raise it\.$/,
    "تم بلوغ الحد: {1}/{2} من حسابات العملاء. اطلب من مدير المنصة رفعه."],
  [/^Limit reached: (\d+)\/(\d+) vendor accounts\. Ask the platform admin to raise it\.$/,
    "تم بلوغ الحد: {1}/{2} من حسابات المورّدين. اطلب من مدير المنصة رفعه."],
  [/^Login limit reached \((\d+)\/(\d+)\) for this account\.(?: Ask the platform admin to raise it\.)?$/,
    "تم بلوغ حد حسابات الدخول ({1}/{2}) لهذا الحساب."],
  [/^\+(\d+) is already linked to (.+)$/, "الرقم ‎+{1} مرتبط مسبقاً بـ {2}"],
  [/^Not a valid WhatsApp number: (.+)\. Write it with the country code, for example \+968 9123 4567$/,
    "رقم واتساب غير صحيح: {1}. اكتبه مع رمز الدولة، مثل ‎+968 9123 4567"],
  [/^The platform admin has not allowed: (.+)$/, "لم يسمح مدير المنصة بـ: {1}"],
  [/^Not a feature of this kind of account: (.+)$/, "ليست ميزة لهذا النوع من الحسابات: {1}"],
];
