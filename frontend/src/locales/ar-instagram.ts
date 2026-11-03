/** Arabic texts of the Instagram Direct channel: "Connect Instagram" (settings and platform console),
 *  the inbox, the dashboard, and the server's Instagram messages. English text is the key. */
export const AR_INSTAGRAM: Record<string, string> = {
  // Names and navigation
  "Instagram": "إنستغرام",
  "AI & channels": "الذكاء الاصطناعي والقنوات",
  "One AI brain, your own persona and knowledge, on your page, WhatsApp and Instagram.":
    "عقل ذكي واحد، بشخصيتك ومعلوماتك، على صفحتك وواتساب وإنستغرام.",
  "{name} answers your customers on your page, on WhatsApp and on Instagram. Its knowledge, personality, welcome messages and trained answers are all in AI training, with a test chat to try it.":
    "{name} يرد على عملائك في صفحتك وعلى واتساب وإنستغرام. معلوماته وشخصيته ورسائل الترحيب والإجابات المدرّبة كلها في تدريب الذكاء الاصطناعي، مع محادثة تجريبية لتجربته.",

  // Connect Instagram card
  "Connect Instagram": "ربط إنستغرام",
  "Needs access token": "يحتاج رمز الوصول",
  "Customers who send a Direct Message to your Instagram account talk to your AI consultant, and your team sees and answers the chats in Conversations, like WhatsApp.":
    "العملاء الذين يرسلون رسالة مباشرة إلى حسابك على إنستغرام يتحدثون مع مستشارك الذكي، وفريقك يرى المحادثات ويرد عليها في المحادثات، تماماً مثل واتساب.",
  "This company's Instagram Direct connection. You can set it up for the company here: you may assign an account ID without Instagram's ownership check, but never one used by another company.":
    "ربط رسائل إنستغرام المباشرة لهذه الشركة. يمكنك إعداده للشركة هنا: يمكنك تعيين معرّف حساب دون تحقق إنستغرام من الملكية، لكن ليس حساباً مستخدماً لدى شركة أخرى.",
  "Instagram account:": "حساب إنستغرام:",
  "Account ID:": "معرّف الحساب:",
  "The company's Instagram webhook (Callback URL):": "عنوان Webhook لإنستغرام الخاص بالشركة (Callback URL):",
  "Instagram's 24-hour window": "نافذة الـ 24 ساعة في إنستغرام",
  "Your AI and your team can answer a customer for 24 hours after their last message.":
    "يستطيع مساعدك الذكي وفريقك الرد على العميل خلال 24 ساعة من آخر رسالة منه.",
  "After that Instagram refuses replies until the customer writes again. Conversations shows when the window has ended.":
    "بعد ذلك يرفض إنستغرام الردود حتى يكتب العميل من جديد. تظهر صفحة المحادثات متى انتهت النافذة.",
  "Instagram does not share the customer's phone number: the AI asks for it before it books a trip.":
    "إنستغرام لا يشارك رقم هاتف العميل: يطلبه المساعد الذكي قبل حجز الرحلة.",

  // Steps
  "An Instagram professional account": "حساب إنستغرام احترافي",
  "Meta only connects Business or Creator accounts. In the Instagram app: Settings → Account type and tools → Switch to professional account.":
    "تربط Meta حسابات الأعمال أو صناع المحتوى فقط. في تطبيق إنستغرام: الإعدادات ← نوع الحساب والأدوات ← التبديل إلى حساب احترافي.",
  "Allow access to messages": "السماح بالوصول إلى الرسائل",
  "in the Instagram app: Settings → Messages and story replies → Message controls → Connected tools → turn on Allow access to messages.":
    "في تطبيق إنستغرام: الإعدادات ← الرسائل والردود على القصص ← عناصر التحكم في الرسائل ← الأدوات المتصلة ← فعّل السماح بالوصول إلى الرسائل.",
  "A Meta app with Instagram": "تطبيق Meta مع إنستغرام",
  "on {site}: My Apps → Create app → Business, then add the product {product}.":
    "على {site}: تطبيقاتي ← إنشاء تطبيق ← أعمال، ثم أضف المنتج {product}.",
  "in your app → Instagram → API setup with Instagram login → Generate access tokens → Add account, log in with your business Instagram account, then Generate token. It needs {perms}.":
    "في تطبيقك ← Instagram ← API setup with Instagram login ← Generate access tokens ← Add account، سجّل الدخول بحساب إنستغرام التجاري، ثم Generate token. يحتاج الصلاحيات {perms}.",
  "Instagram app secret": "المفتاح السري لتطبيق إنستغرام",
  "on the same page, under Instagram app ID → Instagram app secret → Show. It is not the Facebook app secret.":
    "في الصفحة نفسها، تحت Instagram app ID ← Instagram app secret ← Show. وهو ليس المفتاح السري لتطبيق فيسبوك.",
  "The long token from Generate token. It is renewed automatically while customers write to you.":
    "الرمز الطويل من Generate token. يُجدَّد تلقائياً ما دام العملاء يراسلونك.",
  "Required: without it Instagram messages are refused.": "مطلوب: بدونه تُرفض رسائل إنستغرام.",
  "Instagram account ID": "معرّف حساب إنستغرام",
  "Leave empty: it is read from your access token. If you type it, Instagram must confirm it belongs to your token, so nobody can connect an account that isn't theirs.":
    "اتركه فارغاً: يُقرأ من رمز الوصول. إن كتبته فيجب أن يؤكد إنستغرام أنه تابع لرمزك، حتى لا يربط أحد حساباً ليس له.",
  "Instagram settings saved.": "تم حفظ إعدادات إنستغرام.",
  "Save Instagram settings": "حفظ إعدادات إنستغرام",
  "Disconnect Instagram? Direct messages stop reaching your AI and your team until you connect again.":
    "فصل إنستغرام؟ لن تصل الرسائل المباشرة إلى مساعدك الذكي وفريقك حتى تربطه من جديد.",
  "Disconnect": "فصل",
  "In your app → Instagram → API setup with Instagram login → Configure webhooks, paste:":
    "في تطبيقك ← Instagram ← API setup with Instagram login ← Configure webhooks، الصق:",
  "Click Verify and save. Then subscribe to the {field} webhook field.":
    "اضغط Verify and save. ثم اشترك في حقل Webhook المسمى {field}.",
  "Until Meta approves your app (App Review of {perm}) and it is Live, only people with a role in your app reach the AI.":
    "حتى توافق Meta على تطبيقك (مراجعة التطبيق لصلاحية {perm}) ويصبح في وضع Live، لا يصل إلى المساعد الذكي إلا من لهم دور في تطبيقك.",
  "Save your Instagram app secret in step 2 first: messages sent to this address are refused without it.":
    "احفظ المفتاح السري لتطبيق إنستغرام في الخطوة 2 أولاً: تُرفض الرسائل المرسلة إلى هذا العنوان بدونه.",

  // Platform console
  "Set up Instagram for this company": "إعداد إنستغرام لهذه الشركة",
  "The company's own Meta app sends and signs the messages: it needs the access token and the Instagram app secret of that app.":
    "تطبيق Meta الخاص بالشركة يرسل الرسائل ويوقّعها: يحتاج رمز الوصول والمفتاح السري لتطبيق إنستغرام لذلك التطبيق.",
  "Leave the token and secret empty to keep the saved ones.": "اترك الرمز والمفتاح السري فارغين للإبقاء على المحفوظ.",
  "Instagram username": "اسم المستخدم في إنستغرام",
  "Shown to the team, for example {example}": "يظهر للفريق، مثل {example}",
  "No access token saved.": "لم يُحفظ رمز وصول.",

  // Test connection
  "Asks Instagram which account the access token belongs to, and whether it is the connected one.":
    "يسأل إنستغرام لأي حساب يتبع رمز الوصول، وهل هو الحساب المربوط.",
  "Messages from customers still need the Instagram app secret (step 2).":
    "رسائل العملاء ما زالت تحتاج المفتاح السري لتطبيق إنستغرام (الخطوة 2).",
  "Connect @{username}": "اربط ‎@{username}",
  "Connect this account": "اربط هذا الحساب",

  // Inbox
  "Saved, but Instagram did not deliver it. Check the Instagram connection in Settings, or try again.":
    "تم الحفظ، لكن إنستغرام لم يوصلها. تحقق من ربط إنستغرام في الإعدادات، أو حاول مرة أخرى.",
  "Instagram's 24-hour window has ended": "انتهت نافذة الـ 24 ساعة في إنستغرام",
  "Instagram only allows replies within 24 hours of the customer's last message. Wait for them to write again, or call them if they gave a phone number.":
    "يسمح إنستغرام بالرد خلال 24 ساعة فقط من آخر رسالة للعميل. انتظر حتى يكتب من جديد، أو اتصل به إن أعطاك رقم هاتفه.",

  // Dashboard
  "{web} website · {wa} WhatsApp · {ig} Instagram": "{web} من الموقع · {wa} من واتساب · {ig} من إنستغرام",
  "{web} website, {wa} WhatsApp and {ig} Instagram conversations in the last {period}. Use the arrow keys for each day.":
    "{web} محادثة من الموقع و{wa} من واتساب و{ig} من إنستغرام خلال آخر {period}. استخدم مفاتيح الأسهم لكل يوم.",

  // Server messages (shown as they come from the server)
  "Instagram only allows replies within 24 hours of the customer's last message. Wait until they write again, or contact them another way.":
    "يسمح إنستغرام بالرد خلال 24 ساعة فقط من آخر رسالة للعميل. انتظر حتى يكتب من جديد، أو تواصل معه بطريقة أخرى.",
  "This Instagram account is already connected to another company": "حساب إنستغرام هذا مربوط بشركة أخرى",
  "This WhatsApp number or Instagram account is already connected to another company":
    "رقم واتساب أو حساب إنستغرام هذا مربوط بشركة أخرى",
  "Add your Instagram access token to connect an Instagram account": "أضف رمز الوصول لإنستغرام لربط حساب إنستغرام",
  "Instagram did not confirm this account ID for your access token. Use Test connection to see the exact problem.":
    "لم يؤكد إنستغرام معرّف الحساب هذا لرمز الوصول الخاص بك. استخدم اختبار الاتصال لمعرفة المشكلة بالضبط.",
  "Connected: Instagram confirmed that this access token belongs to this account.":
    "متصل: أكد إنستغرام أن رمز الوصول هذا تابع لهذا الحساب.",
  "The access token is not valid or has expired. Generate a new token for your Instagram account in your Meta app (Instagram → API setup with Instagram login) and save it again.":
    "رمز الوصول غير صالح أو منتهي. أنشئ رمزاً جديداً لحساب إنستغرام في تطبيق Meta (Instagram ← API setup with Instagram login) واحفظه مرة أخرى.",
  "This access token belongs to another Instagram account. Generate the token while logged in to the account you want to connect, or correct the account ID.":
    "رمز الوصول هذا تابع لحساب إنستغرام آخر. أنشئ الرمز وأنت مسجل الدخول بالحساب الذي تريد ربطه، أو صحّح معرّف الحساب.",
  "The access token works. Save the Instagram account ID it belongs to (shown below) to finish connecting.":
    "رمز الوصول يعمل. احفظ معرّف حساب إنستغرام التابع له (الظاهر بالأسفل) لإكمال الربط.",
  "This access token is missing the Instagram messaging permission. Generate it again with instagram_business_basic and instagram_business_manage_messages.":
    "رمز الوصول هذا تنقصه صلاحية رسائل إنستغرام. أنشئه مرة أخرى مع instagram_business_basic و instagram_business_manage_messages.",
  "Could not reach Instagram. Check the internet connection of the server and try again.":
    "تعذر الوصول إلى إنستغرام. تحقق من اتصال الخادم بالإنترنت وحاول مرة أخرى.",
  "Add the Instagram access token first.": "أضف رمز الوصول لإنستغرام أولاً.",
};
