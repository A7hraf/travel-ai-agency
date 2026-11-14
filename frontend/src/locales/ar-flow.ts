/** Arabic texts of the request flow: the Requests page (request card, quotation, priority), the Services page and
 *  the quotation stage of the client's trips page. English text is the key. (ar.ts merges AR_FLOW into AR.) */
export const AR_FLOW: Record<string, string> = {
  // Requests page
  "Requests": "الطلبات",
  "Request": "الطلب",
  "Waiting for us": "بانتظارنا",
  "No requests yet. They appear here when the AI sends a request card or books a package.":
    "لا توجد طلبات بعد. تظهر هنا عندما يرسل الذكاء الاصطناعي بطاقة طلب أو يحجز باقة.",
  "New request": "طلب جديد",
  "Choices sent": "أُرسلت الخيارات",
  "Changes asked": "طلب تعديلات",
  "Client chose": "اختار العميل",
  "Final quotation sent": "أُرسل عرض السعر النهائي",
  "Rejected by the client": "رفضه العميل",
  "Checking payment": "مراجعة الدفع",
  "Reopen request": "إعادة فتح الطلب",
  "Urgent": "عاجل",
  "Soon": "قريب",
  "trip in {n} days": "الرحلة بعد {n} يوم",
  "waiting {n} days": "ينتظر منذ {n} يوم",
  "waiting {n} hours": "ينتظر منذ {n} ساعة",
  "high value": "قيمة عالية",
  "{level} member": "عضو {level}",
  "Priority {n}/100": "الأولوية {n}/100",
  "The client rejected the quotation.": "رفض العميل عرض السعر.",
  "Cancelled.": "أُلغي.",
  "{who} added the choice {new}": "أضاف {who} الخيار {new}",
  "{who} changed the choice {new}": "عدّل {who} الخيار {new}",
  "{who} removed the choice {new}": "حذف {who} الخيار {new}",
  "{who} let the AI draft choices ({new})": "طلب {who} من الذكاء الاصطناعي اقتراح خيارات ({new})",
  "{who} picked: {new}": "اختار {who}: {new}",
  "{who} asked for changes: {new}": "طلب {who} تعديلات: {new}",
  "{who} added to the final quotation: {new}": "أضاف {who} إلى عرض السعر النهائي: {new}",
  "Moved from the old requests": "نُقل من الطلبات القديمة",

  "The client is told in the chat. Only a company admin can reopen it.": "يُبلَّغ العميل في المحادثة. لا يعيد فتحه إلا مدير الشركة.",

  // Request card
  "Request card": "بطاقة الطلب",
  "Quotation round {n}": "جولة عرض السعر {n}",
  "The client asked for changes:": "طلب العميل تعديلات:",

  // Quotation
  "Quotation": "عرض السعر",
  "Visa": "التأشيرة",
  "Insurance": "التأمين",
  "Other": "أخرى",
  "Draft choices with AI": "اقترح الخيارات بالذكاء الاصطناعي",
  "Tick up to 3 choices per part. Every choice sent needs its client price; AI estimates are for you only.":
    "حدّد حتى 3 خيارات لكل جزء. كل خيار يُرسل يحتاج سعره للعميل؛ تقديرات الذكاء الاصطناعي لك أنت فقط.",
  "No choices yet.": "لا توجد خيارات بعد.",
  "Link (Booking.com, airline, activity page)": "الرابط (Booking.com، شركة الطيران، صفحة النشاط)",
  "Link": "الرابط",
  "Your cost": "تكلفتك",
  "Details for the client (times, room type, conditions…)": "تفاصيل للعميل (المواعيد، نوع الغرفة، الشروط…)",
  "Add choice": "أضف خياراً",
  "Open link": "افتح الرابط",
  "sent": "أُرسل",
  "chosen by the client": "اختاره العميل",
  "No price": "بلا سعر",
  "Final quotation": "عرض السعر النهائي",
  "Final total": "المجموع النهائي",
  "Note for the client": "ملاحظة للعميل",
  "Note for the client (optional)": "ملاحظة للعميل (اختياري)",
  "Send the final quotation": "أرسل عرض السعر النهائي",
  "The client answered by phone or in person?": "ردّ العميل بالهاتف أو حضورياً؟",
  "The client's answer": "رد العميل",
  "Choose the answer": "اختر الرد",
  "Picked choices (mark them above)": "اختار من الخيارات (حدّدها في الأعلى)",
  "The client picked {name}": "اختار العميل {name}",
  "Asked for changes": "طلب تعديلات",
  "Approved the final quotation": "وافق على عرض السعر النهائي",
  "Rejected": "رفض",
  "Paid (transfer number below)": "دفع (رقم التحويل في الأسفل)",
  "Cancelled the request": "ألغى الطلب",
  "Transfer or receipt number": "رقم التحويل أو الإيصال",
  "What the client said": "ما قاله العميل",
  "Save the client's answer": "احفظ رد العميل",

  // Services page
  "What your company offers. For each service, the AI asks the client your questions, follows your rules and sends your team a request card.":
    "ما تقدمه شركتك. في كل خدمة يسأل الذكاء الاصطناعي العميل أسئلتك، ويتبع قواعدك، ويرسل لفريقك بطاقة طلب.",
  "Describe a service to the AI": "صف خدمة للذكاء الاصطناعي",
  "e.g. We arrange Schengen visas. We need passport copy, travel dates, bank statement. Fee 45 OMR. Takes 15 working days, no refund after submitting.":
    "مثال: نستخرج تأشيرات شنغن. نحتاج صورة الجواز، وتواريخ السفر، وكشف حساب بنكي. الرسوم 45 ر.ع. المدة 15 يوم عمل، ولا استرداد بعد التقديم.",
  "Add by hand": "أضف يدوياً",
  "Build the service": "أنشئ الخدمة",
  "Check the draft, then save it. Nothing is saved yet.": "راجع المسودة ثم احفظها. لم يُحفظ شيء بعد.",
  "Switched off": "متوقفة",
  "{n} questions": "{n} سؤال",
  "Fixed price": "سعر ثابت",
  "Priced per request (quotation)": "يُسعّر لكل طلب (عرض سعر)",
  "Ready-made packages": "باقات جاهزة",
  "How the price is set": "كيف يُحدَّد السعر",
  "e.g. flights at cost + 15 OMR per person": "مثال: الطيران بالتكلفة + 15 ر.ع للشخص",
  "Clients book your ready-made packages directly: the price and seats come from the Packages page.":
    "يحجز العملاء باقاتك الجاهزة مباشرة: السعر والمقاعد من صفحة الباقات.",
  "What the quotation contains": "ما يحتويه عرض السعر",
  "Questions the AI asks the client": "الأسئلة التي يطرحها الذكاء الاصطناعي على العميل",
  "Question (English)": "السؤال (بالإنجليزية)",
  "Question (Arabic)": "السؤال (بالعربية)",
  "Answer type": "نوع الإجابة",
  "Short text": "نص قصير",
  "Long text": "نص طويل",
  "Number": "رقم",
  "Choice": "اختيار",
  "Required": "إلزامي",
  "Choices, separated by commas": "الخيارات، مفصولة بفواصل",
  "Add a question": "أضف سؤالاً",
  "Booking steps after payment": "خطوات الحجز بعد الدفع",
  "Step (English)": "الخطوة (بالإنجليزية)",
  "Step (Arabic)": "الخطوة (بالعربية)",
  "Add a step": "أضف خطوة",
  "Rules and exceptions (the AI follows them)": "القواعد والاستثناءات (يلتزم بها الذكاء الاصطناعي)",
  "e.g. Visa requests need 10 working days. No refunds after the visa is issued.":
    "مثال: طلبات التأشيرة تحتاج 10 أيام عمل. لا استرداد بعد صدور التأشيرة.",
  "Offered to clients": "متاحة للعملاء",
  "Switched off, the AI no longer offers it. Old requests stay.": "عند إيقافها لا يعرضها الذكاء الاصطناعي. تبقى الطلبات السابقة.",
  "Save the service": "احفظ الخدمة",
  "How clients pay": "طريقة دفع العملاء",
  "Sent to the client when they approve the final quotation: bank name, account or IBAN, and what to write in the transfer.":
    "تُرسل للعميل عند موافقته على عرض السعر النهائي: اسم البنك، ورقم الحساب أو الآيبان، وما يكتبه في التحويل.",

  // Members and business requests
  "The AI takes their requests beyond the packages (yacht, restaurant, surprise…) and sends your team a request card on the Requests page.":
    "يستقبل الذكاء الاصطناعي طلباتهم خارج الباقات (يخت، مطعم، مفاجأة…) ويرسل لفريقك بطاقة طلب في صفحة الطلبات.",
  "Trips asked by your business clients. Let the AI draft options or ask a vendor, send up to 3 choices per part, approve, and track the booking.":
    "رحلات يطلبها عملاؤك من الشركات. دع الذكاء الاصطناعي يقترح الخيارات أو اطلبها من مورّد، وأرسل حتى 3 خيارات لكل جزء، ثم اعتمد وتابع الحجز.",

  // Client trips page
  "Requested": "تم الطلب",
  "We are preparing your choices.": "نجهّز لك الخيارات.",
  "Your choices are ready: answer us in the chat.": "خياراتك جاهزة: ردّ علينا في المحادثة.",
  "We are updating your choices.": "نعدّل لك الخيارات.",
  "We are preparing your final quotation.": "نجهّز عرض السعر النهائي.",
  "Your final quotation is ready: approve it in the chat.": "عرض السعر النهائي جاهز: وافق عليه في المحادثة.",

  // Insights
  "Quotations approved": "عروض الأسعار المعتمدة",
  "Approval {p} · {n} rounds on average": "نسبة الاعتماد {p} · {n} جولة في المتوسط",

  // Server messages
  "Service not found": "الخدمة غير موجودة",
  "Ready-made packages are one built-in service": "الباقات الجاهزة خدمة مدمجة واحدة",
  "A company can have at most 50 services": "يمكن للشركة إضافة 50 خدمة كحد أقصى",
  "Only the built-in packages service works with ready-made packages": "خدمة الباقات المدمجة وحدها تعمل مع الباقات الجاهزة",
  "Built-in services and services with requests can't be deleted: switch them off instead":
    "لا يمكن حذف الخدمات المدمجة أو التي لها طلبات: أوقفها بدلاً من ذلك",
  "The AI could not build the service right now. Please try again.": "تعذّر على الذكاء الاصطناعي إنشاء الخدمة الآن. حاول مرة أخرى.",
  "The link must start with https://": "يجب أن يبدأ الرابط بـ https://",
  "Could not create the request, please try again": "تعذّر إنشاء الطلب، حاول مرة أخرى",
  "This request has no parts to draft, or already has the most options": "لا توجد أجزاء لاقتراحها في هذا الطلب، أو بلغ الحد الأقصى للخيارات",
  "Set the final total first": "حدّد المجموع النهائي أولاً",
  "Say what should change": "اذكر ما يجب تعديله",
  "Give the transfer or receipt number": "أدخل رقم التحويل أو الإيصال",
  "Two questions have the same key": "سؤالان لهما المفتاح نفسه",
  "Two booking steps have the same key": "خطوتا حجز لهما المفتاح نفسه",
  "A fixed-price service needs its price": "الخدمة بسعر ثابت تحتاج سعرها",
};

export const AR_FLOW_PATTERNS: [RegExp, string][] = [
  [/^This request is now '(\w+)', so this step is not possible\.$/, "الطلب الآن «{1:status}»، لذا لا يمكن تنفيذ هذه الخطوة."],
  [/^A request can have at most (\d+) options$/, "يمكن أن يحتوي الطلب على {1} خياراً كحد أقصى"],
  [/^Send at most (\d+) choices for each part$/, "أرسل {1} خيارات كحد أقصى لكل جزء"],
  [/^Set the client price of "(.+)" first$/, "حدّد سعر العميل لـ «{1}» أولاً"],
  [/^Missing: (.+)$/, "ناقص: {1}"],
];
