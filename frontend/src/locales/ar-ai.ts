/** Arabic texts of AI training ("Answers", "Company knowledge", "Try your AI") and the
 *  "Connect WhatsApp" steps. English text is the key; server messages are translated by their exact text. */
export const AR_AI: Record<string, string> = {
  // Training tabs and how it works
  "Company knowledge": "معلومات الشركة",
  "Try your AI": "جرّب مساعدك الذكي",
  "How AI training works": "كيف يعمل تدريب الذكاء الاصطناعي",
  "Your AI consultant already knows your packages (titles, prices, dates, descriptions). Training teaches it everything else about your company, in plain words. No technical skills needed.":
    "مستشارك الذكي يعرف باقاتك مسبقاً (العناوين والأسعار والتواريخ والأوصاف). التدريب يعلّمه كل ما عدا ذلك عن شركتك بكلمات بسيطة، دون أي خبرة تقنية.",
  "Teach answers": "علّمه الإجابات",
  "Write the questions customers ask you and your company's answer. When a customer asks something similar, in Arabic or English, the AI answers your way.":
    "اكتب الأسئلة التي يطرحها العملاء وإجابة شركتك عليها. عندما يسأل عميل سؤالاً مشابهاً، بالعربية أو الإنجليزية، يجيب المساعد بطريقتك.",
  "Add an answer": "أضف إجابة",
  "Add company knowledge": "أضف معلومات الشركة",
  "Paste your policies: payment, deposit, cancellation, visas, office hours. The AI uses them and never contradicts them.":
    "الصق سياساتك: الدفع والعربون والإلغاء والتأشيرات وساعات العمل. يستخدمها المساعد ولا يخالفها أبداً.",
  "Add knowledge": "أضف المعلومات",
  "Ask a question as if you were a customer and see the real answer. If it's not right, correct it and teach it in one click.":
    "اسأل كأنك عميل وشاهد الإجابة الحقيقية. إن لم تكن صحيحة، صحّحها وعلّمها للمساعد بضغطة واحدة.",
  "Each company's training is private: it is never used for another company.": "تدريب كل شركة خاص بها: لا يُستخدم أبداً لشركة أخرى.",

  // Answers and import
  "Import many answers": "استيراد إجابات كثيرة",
  "Tip: start with 5 to 10 questions, such as payment, deposit, visas and what's included.":
    "نصيحة: ابدأ بـ 5 إلى 10 أسئلة، مثل الدفع والعربون والتأشيرات وما تشمله الباقة.",
  "Paste one answer per line: the question, a | sign, then the answer. You can also paste two columns copied from Excel or Google Sheets, or a CSV file's text. Up to 200 at a time.":
    "الصق إجابة في كل سطر: السؤال ثم علامة | ثم الإجابة. يمكنك أيضاً لصق عمودين منسوخين من Excel أو Google Sheets، أو نص ملف CSV. حتى 200 في كل مرة.",
  "Questions and answers": "الأسئلة والإجابات",
  "Example:": "مثال:",
  "{n} answers added to the training.": "أُضيفت {n} إجابة إلى التدريب.",
  "{n} new answers": "{n} إجابة جديدة",
  "{n} already trained (skipped)": "{n} موجودة مسبقاً (تم تخطيها)",
  "{n} lines with a problem (skipped)": "{n} سطر فيه مشكلة (تم تخطيه)",
  "Line {n}": "السطر {n}",
  "Import {n} answers": "استيراد {n} إجابة",
  "Checking…": "جارٍ الفحص…",
  "Check the lines": "افحص الأسطر",

  // Company knowledge
  "What the AI should know about your company and how it should behave. It applies to the website chat and WhatsApp.":
    "ما يجب أن يعرفه المساعد عن شركتك وكيف يتصرف. ينطبق على محادثة الموقع وواتساب.",
  "e.g. We take a 20% deposit to book. Cancellation is free up to 30 days before departure. Office hours: Sat–Thu 9am–6pm.":
    "مثال: نأخذ عربوناً 20% للحجز. الإلغاء مجاني حتى 30 يوماً قبل السفر. ساعات العمل: السبت–الخميس 9 صباحاً–6 مساءً.",
  "Personality": "الشخصية",
  "Save knowledge": "حفظ المعلومات",

  // Try your AI
  "The AI could not answer.": "لم يتمكن المساعد من الإجابة.",
  "Test mode": "وضع التجربة",
  "New test chat": "محادثة تجربة جديدة",
  "Type a question as if you were a customer, in Arabic or English. You get the real answer with your packages, knowledge and trained answers. Nothing is saved: no chat, customer or booking is created.":
    "اكتب سؤالاً كأنك عميل، بالعربية أو الإنجليزية. تحصل على الإجابة الحقيقية من باقاتك ومعلوماتك وإجاباتك المدرّبة. لا يُحفظ شيء: لا تُنشأ محادثة أو عميل أو حجز.",
  "Ask your AI anything a customer would ask": "اسأل مساعدك أي شيء قد يسأله العميل",
  "You (as a customer)": "أنت (كعميل)",
  "Teach this answer": "علّمه هذه الإجابة",
  "Thinking…": "يفكّر…",
  "Write a customer question…": "اكتب سؤال العميل…",
  "No trained answer matched this question.": "لا توجد إجابة مدرّبة تطابق هذا السؤال.",
  "Trained answers used:": "الإجابات المدرّبة المستخدمة:",
  "Packages it looked at:": "الباقات التي اطّلع عليها:",
  "Test mode: in a real chat a booking ticket would be created here for your team. Nothing was booked and no seats were held.":
    "وضع التجربة: في محادثة حقيقية تُنشأ هنا تذكرة حجز لفريقك. لم يُحجز شيء ولم تُحجز أي مقاعد.",
  "Test mode: in a real chat the customer would be handed to your team here.": "وضع التجربة: في محادثة حقيقية يُحوَّل العميل هنا إلى فريقك.",
  "Taught! Ask the question again to see the new answer.": "تم التعليم! اسأل السؤال مرة أخرى لترى الإجابة الجديدة.",
  "Correct the answer if needed. The AI will answer this way when a customer asks something similar.":
    "صحّح الإجابة إن لزم. سيجيب المساعد بهذه الطريقة عندما يسأل عميل سؤالاً مشابهاً.",
  "Correct answer": "الإجابة الصحيحة",
  "Save to training": "حفظ في التدريب",
  "AI & WhatsApp settings": "إعدادات الذكاء الاصطناعي وواتساب",
  "{name} answers your customers on your page and on WhatsApp. Its knowledge, personality, welcome messages and trained answers are now all in AI training, with a test chat to try it.":
    "{name} يجيب عملاءك في صفحتك وعلى واتساب. معلوماته وشخصيته ورسائل الترحيب والإجابات المدرّبة أصبحت كلها في تدريب الذكاء الاصطناعي، مع محادثة تجربة لاختباره.",
  "Train your AI": "درّب مساعدك",

  // WhatsApp
  "Needs app secret": "يحتاج سر التطبيق",
  "Needs the platform token": "يحتاج رمز المنصة",
  "Not connected": "غير متصل",
  "Connect WhatsApp": "ربط واتساب",
  "Customers who message your WhatsApp number talk to your AI consultant, and your team sees the chats in Conversations. Choose how to connect:":
    "العملاء الذين يراسلون رقم واتساب الخاص بك يتحدثون مع مستشارك الذكي، ويرى فريقك المحادثات في صفحة المحادثات. اختر طريقة الربط:",
  "This company's WhatsApp connection. You can assign a number of the platform's Meta app, or the company connects its own Meta app in its settings.":
    "ربط واتساب لهذه الشركة. يمكنك تخصيص رقم من تطبيق Meta الخاص بالمنصة، أو تربط الشركة تطبيق Meta الخاص بها من إعداداتها.",
  "Phone number ID:": "معرّف رقم الهاتف:",
  "on the platform's WhatsApp app": "على تطبيق واتساب الخاص بالمنصة",
  "on the company's own Meta app": "على تطبيق Meta الخاص بالشركة",
  "How to connect": "طريقة الربط",
  "My own WhatsApp Business number": "رقم واتساب أعمال خاص بي",
  "Your number, your Meta app. About 20 minutes, following the 4 steps below.": "رقمك وتطبيق Meta الخاص بك. حوالي 20 دقيقة باتباع الخطوات الأربع أدناه.",
  "Use the platform's WhatsApp number": "استخدام رقم واتساب المنصة",
  "Nothing to set up: the platform owner connects a number for you.": "لا شيء لإعداده: مالك المنصة يربط رقماً لك.",
  "The company's own webhook (if it uses its own Meta app):": "عنوان Webhook الخاص بالشركة (إن كانت تستخدم تطبيق Meta الخاص بها):",
  "Access token saved by the company.": "رمز الوصول محفوظ من الشركة.",
  "No access token saved by the company.": "لم تحفظ الشركة رمز وصول.",
  "App secret saved.": "سر التطبيق محفوظ.",
  "No app secret saved.": "لم يُحفظ سر التطبيق.",
  "The platform's WhatsApp number": "رقم واتساب المنصة",
  "The platform owner adds a WhatsApp number to the platform's Meta app and assigns it to your company. Ask the platform owner for it.":
    "يضيف مالك المنصة رقم واتساب إلى تطبيق Meta الخاص بالمنصة ويخصصه لشركتك. اطلبه من مالك المنصة.",
  "You don't need a Meta account, token or webhook: messages to that number reach your AI and your team automatically.":
    "لا تحتاج حساب Meta أو رمزاً أو Webhook: الرسائل إلى ذلك الرقم تصل إلى مساعدك وفريقك تلقائياً.",
  "Once it is assigned, it shows here as connected. You can still switch to your own number later.":
    "بعد تخصيصه يظهر هنا كمتصل. ويمكنك لاحقاً التحويل إلى رقمك الخاص.",
  "A platform number is assigned to your company.": "تم تخصيص رقم من المنصة لشركتك.",
  "No platform number is assigned to your company yet.": "لم يُخصص رقم من المنصة لشركتك بعد.",
  "Get these from Meta": "احصل على هذه من Meta",
  "A Meta Business account": "حساب Meta للأعمال",
  "A Meta app with WhatsApp": "تطبيق Meta مع واتساب",
  "on {site}: My Apps → Create app → Business, then add the WhatsApp product.": "في {site}: My Apps ← Create app ← Business، ثم أضف منتج WhatsApp.",
  "in your app → WhatsApp → API Setup, add and verify your business number, then copy its Phone number ID (a long number, not the phone number). The WhatsApp Business Account ID is not needed here.":
    "في تطبيقك ← WhatsApp ← API Setup، أضف رقم عملك وأكّده، ثم انسخ Phone number ID (رقم طويل، وليس رقم الهاتف). لا حاجة هنا إلى معرّف حساب واتساب للأعمال.",
  "Permanent access token": "رمز وصول دائم",
  "Business settings → Users → System users → Add, give it your app and WhatsApp account, then Generate token with {perms}. The temporary token of API Setup stops after 24 hours.":
    "إعدادات الأعمال ← Users ← System users ← Add، امنحه تطبيقك وحساب واتساب، ثم Generate token بالصلاحيات {perms}. الرمز المؤقت في API Setup يتوقف بعد 24 ساعة.",
  "in your app → App settings → Basic → App secret → Show.": "في تطبيقك ← App settings ← Basic ← App secret ← Show.",
  "Enter them here": "أدخلها هنا",
  "Checked with Meta using your access token, so nobody can connect a number that isn't theirs.":
    "يُتحقق منه لدى Meta برمز الوصول الخاص بك، حتى لا يستطيع أحد ربط رقم ليس له.",
  "Point Meta's webhook to your AI": "وجّه Webhook في Meta إلى مساعدك",
  "In your app → WhatsApp → Configuration → Webhook → Edit, paste:": "في تطبيقك ← WhatsApp ← Configuration ← Webhook ← Edit، الصق:",
  "Click Verify and save. Then, under Webhook fields, click Manage and subscribe to {field}.":
    "اضغط Verify and save. ثم في Webhook fields اضغط Manage واشترك في الحقل {field}.",
  "Keep these private.": "احتفظ بها سرية.",
  "Save your app secret in step 2 first: messages sent to this address are refused without it.":
    "احفظ سر التطبيق في الخطوة 2 أولاً: تُرفض الرسائل المرسلة إلى هذا العنوان بدونه.",
  "Test the connection": "اختبر الربط",
  "Platform WhatsApp number": "رقم واتساب المنصة",
  "Add the number to the platform's own Meta app (WhatsApp → API Setup) and paste its Phone number ID here. Messages to it go to this company's AI and team.":
    "أضف الرقم إلى تطبيق Meta الخاص بالمنصة (WhatsApp ← API Setup) والصق Phone number ID هنا. الرسائل إليه تذهب إلى مساعد هذه الشركة وفريقها.",
  "The platform's WhatsApp token is set on the server.": "رمز واتساب الخاص بالمنصة مُعدّ على الخادم.",
  "The platform's WhatsApp token is not set on the server (WHATSAPP_DEFAULT_ACCESS_TOKEN), so platform numbers can't send messages yet.":
    "رمز واتساب الخاص بالمنصة غير مُعدّ على الخادم (WHATSAPP_DEFAULT_ACCESS_TOKEN)، لذلك لا تستطيع أرقام المنصة إرسال الرسائل بعد.",
  "This company already connected its own number. Assigning a platform number replaces it.": "ربطت هذه الشركة رقمها الخاص. تخصيص رقم من المنصة يستبدله.",
  "Leave empty to disconnect.": "اتركه فارغاً لإلغاء الربط.",
  "Asks Meta whether the access token may use this phone number.": "يسأل Meta إن كان رمز الوصول يستطيع استخدام هذا الرقم.",
  "Test connection": "اختبار الربط",
  "Messages from customers still need the app secret (step 2).": "رسائل العملاء ما زالت تحتاج سر التطبيق (الخطوة 2).",
  "Send a test message to my phone": "إرسال رسالة تجريبية إلى هاتفي",
  "With the country code. First send any message from this phone to your business number: Meta only allows free messages within 24 hours of the customer's last message.":
    "مع رمز الدولة. أرسل أولاً أي رسالة من هذا الهاتف إلى رقم عملك: تسمح Meta بالرسائل الحرة خلال 24 ساعة فقط من آخر رسالة للعميل.",
  "Send test": "إرسال تجربة",

  // Server messages
  "Connected: Meta confirmed this phone number ID for this access token.": "متصل: أكدت Meta معرّف رقم الهاتف هذا لرمز الوصول هذا.",
  "The access token is not valid or has expired. Create a permanent token in Meta Business settings → System users and save it again.":
    "رمز الوصول غير صالح أو منتهي. أنشئ رمزاً دائماً من إعدادات Meta للأعمال ← System users واحفظه من جديد.",
  "Meta could not find this phone number ID. Copy it again from your Meta app → WhatsApp → API Setup.":
    "لم تجد Meta معرّف رقم الهاتف هذا. انسخه من جديد من تطبيق Meta ← WhatsApp ← API Setup.",
  "This access token has no access to this phone number. Give the system user access to the WhatsApp Business account of this number.":
    "رمز الوصول هذا لا يملك صلاحية على هذا الرقم. امنح مستخدم النظام صلاحية على حساب واتساب للأعمال الخاص بهذا الرقم.",
  "Could not reach Meta (WhatsApp). Check the internet connection of the server and try again.":
    "تعذّر الوصول إلى Meta (واتساب). تحقق من اتصال الخادم بالإنترنت وحاول مجدداً.",
  "Add the phone number ID and the access token first.": "أضف معرّف رقم الهاتف ورمز الوصول أولاً.",
  "Enter the phone number with its country code, for example +968 9123 4567": "أدخل رقم الهاتف مع رمز الدولة، مثلاً ‎+968 9123 4567",
  "Connect WhatsApp first: add the phone number ID and the access token.": "اربط واتساب أولاً: أضف معرّف رقم الهاتف ورمز الوصول.",
  "Please wait a minute before sending another test message": "يرجى الانتظار دقيقة قبل إرسال رسالة تجريبية أخرى",
  "Too many test messages. Please try again in an hour.": "رسائل تجريبية كثيرة. حاول مجدداً بعد ساعة.",
  "WhatsApp did not send the test message. First send any message from this phone to your WhatsApp business number (Meta only allows replies within 24 hours), then try again.":
    "لم يُرسل واتساب الرسالة التجريبية. أرسل أولاً أي رسالة من هذا الهاتف إلى رقم واتساب عملك (تسمح Meta بالرد خلال 24 ساعة فقط)، ثم حاول مجدداً.",
  "Test message sent. Check WhatsApp on this phone.": "أُرسلت الرسالة التجريبية. تحقق من واتساب على هذا الهاتف.",
  "Please wait a minute before testing again": "يرجى الانتظار دقيقة قبل الاختبار مرة أخرى",
  "The AI is not available right now.": "المساعد الذكي غير متاح حالياً.",
  "The AI could not produce an answer. In a real chat the customer would be handed to your team.":
    "لم يتمكن المساعد من الإجابة. في محادثة حقيقية يُحوَّل العميل إلى فريقك.",
  "Needs a question and an answer separated by |": "يحتاج سؤالاً وإجابة بينهما علامة |",
  "The question must have 2 to 1000 characters": "يجب أن يكون السؤال من 2 إلى 1000 حرف",
  "The answer can have at most 4000 characters": "يمكن أن تكون الإجابة 4000 حرف كحد أقصى",
  "The text is too long. Import at most 200 answers at a time.": "النص طويل جداً. استورد 200 إجابة كحد أقصى في كل مرة.",
  "Paste at least one line: question | answer": "الصق سطراً واحداً على الأقل: السؤال | الإجابة",
  "Import at most 200 answers at a time.": "استورد 200 إجابة كحد أقصى في كل مرة.",
};
