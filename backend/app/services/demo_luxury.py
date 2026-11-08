"""Content of the "luxury concierge" demo agency: a modern, high-end travel brand that also offers private
concierge and lifestyle services. The same package keys as the family profile are used so the sample chats and
bookings of the demo (services/demo.py) fit both profiles. The policies (deposit, cancellation, payment, office
hours) stay the same as the family profile because some sample chats quote them.
"""

from __future__ import annotations

from ..branding import Branding
from .demo import PackageDef

KNOWLEDGE = """\
WHO WE ARE
- A modern travel brand from Muscat: tailor-made luxury trips, private concierge services and lifestyle management.
- Every trip can be changed: hotels, dates, room types, private guides and experiences are arranged on request.

CONCIERGE AND LIFESTYLE SERVICES
- VIP meet & assist and fast track at Muscat International Airport and abroad.
- Private chauffeurs and luxury cars, yacht and dhow charters, private villas and chalets.
- Restaurant reservations, event and match tickets, spa bookings, personal shopping and gifting.
- Lifestyle management for members: one personal concierge for travel, dining and events all year.
- Concierge requests are handled by our team: the AI collects the details and passes them on.

OFFICE AND CONTACT
- Office: Al Khuwair, Muscat. Open Sunday to Thursday 8:30-17:30 and Saturday 10:00-14:00. Closed on Fridays.
- Visits by appointment. The AI consultant answers 24/7 on the website, WhatsApp and Instagram; our team
  replies during office hours, and members have a direct line to their concierge.
- All trips depart from Muscat International Airport (MCT) unless stated.

PRICES AND BOOKING
- Prices are in Omani rials (OMR), per person in a double room, business class flights included unless stated.
- Children 2-11 years pay the child price. Babies under 2 pay 10% of the adult price (no seat, no bed).
- A 30% deposit confirms the booking. The rest is due 21 days before departure.
- Bookings not paid within 48 hours give their places back to other guests.
- Economy class or a private jet is possible on request (price on request).

PAYMENT METHODS
- Bank transfer (Bank Muscat or Bank Dhofar), a secure card payment link (Visa, Mastercard, Amex), or card at our office.
- We never ask for card numbers in the chat.

CANCELLATION AND CHANGES
- Free cancellation up to 30 days before departure (the deposit is refunded minus 10 OMR per person fees).
- 29-15 days before departure: 50% of the total. 14 days or less: no refund.
- Umrah packages: deposit not refundable once the visa is issued.
- Changing the date is free once, up to 21 days before departure, subject to availability.

VISAS AND DOCUMENTS
- Passports must be valid for at least 6 months after return.
- Our team handles every visa for you. Visa service fee: 8 OMR per person (plus the embassy fee).

TRAVEL INSURANCE
- Recommended for every trip abroad. From 6 OMR per person per week, arranged by our team.
"""

KNOWLEDGE_AR = """\
معلومات بالعربية
- علامة سفر عصرية من مسقط: رحلات فاخرة حسب الطلب، خدمات كونسيرج خاصة وإدارة نمط الحياة.
- خدمات الكونسيرج: استقبال VIP في المطار، سائق خاص وسيارات فاخرة، يخوت، فلل خاصة، حجوزات مطاعم، تذاكر فعاليات ومباريات.
- المكتب: الخوير، مسقط. من الأحد إلى الخميس 8:30 - 5:30 مساءً، والسبت 10 صباحاً - 2 ظهراً. الزيارة بموعد.
- الأسعار بالريال العماني للشخص في غرفة مزدوجة وتشمل طيران درجة رجال الأعمال من مسقط.
- عربون 30% يثبت الحجز، والباقي قبل المغادرة بـ 21 يوماً.
- طرق الدفع: تحويل بنكي، رابط دفع آمن بالبطاقة، أو في المكتب.
- الإلغاء: مجاني حتى 30 يوماً قبل المغادرة، 50% من 29 إلى 15 يوماً، ولا استرداد خلال 14 يوماً.
"""

INSTRUCTIONS = (
    "Speak like a warm, discreet private concierge: elegant, short and personal. Mention the 30% deposit when "
    "the guest is ready to book. Every trip can be tailored: offer to adjust hotels, dates or experiences. "
    "For concierge requests (chauffeurs, yachts, villas, restaurant or event bookings, lifestyle membership), "
    "private jets, groups or custom itineraries, collect the details and hand over to the team."
)

WELCOME_EN = ("Welcome to {company} ✨ I'm Sara, your travel concierge. Tell me where you'd like to escape to, "
              "your dates and who is travelling, and I'll curate the perfect trip for you.")
WELCOME_AR = ("أهلاً بك في {company} ✨ معك سارة، مستشارة السفر الخاصة بك. قل لي وين حاب تسافر، ومتى، ومن معك، "
              "وأنا أنسّق لك رحلة على ذوقك.")

ABOUT_EN = ("{company} is a modern travel brand from Muscat. We design tailor-made journeys, from private island "
            "villas to VIP Umrah, and look after everything around them: chauffeurs, yachts, restaurant tables, "
            "event tickets and lifestyle management. Sara, our AI concierge, answers you any time of the day in "
            "Arabic or English, and our team takes care of the rest.")
ABOUT_AR = ("{company} علامة سفر عصرية من مسقط. نصمم رحلات خاصة حسب ذوقك، من فلل الجزر الخاصة إلى العمرة VIP، "
            "ونهتم بكل التفاصيل حولها: السائق الخاص، اليخوت، حجوزات المطاعم، تذاكر الفعاليات وإدارة نمط الحياة. "
            "سارة، مستشارتنا الذكية، ترد عليك في أي وقت بالعربية أو الإنجليزية، وفريقنا يهتم بالباقي.")


def branding_for(company_name: str) -> dict:
    return Branding.model_validate({
        # Deep olive and cream, a quiet luxury look.
        "primary_color": "#5d6e4c",
        "accent_color": "#d8ccad",
        "bg_color": "#222a20",
        "surface_color": "#2e382b",
        "text_color": "#f1ecdf",
        "highlight_color": "#c9a96b",
        "hero_style": "gradient",
        "hero_title_en": "Escape, beautifully planned.",
        "hero_title_ar": "رحلتك، بتفاصيل تليق بك.",
        "hero_text_en": "Tailor-made luxury trips and private concierge services from Muscat. "
                        "Ask Sara, your travel concierge, she replies in seconds.",
        "hero_text_ar": "رحلات فاخرة حسب الطلب وخدمات كونسيرج خاصة من مسقط. اسأل سارة، مستشارتك الخاصة، ترد خلال ثوانٍ.",
        "about_title_en": f"About {company_name}"[:120],
        "about_title_ar": f"عن {company_name}"[:120],
        "about_en": ABOUT_EN.format(company=company_name),
        "about_ar": ABOUT_AR.format(company=company_name),
        "card_style": "square",
        "cards": {"style": "poster", "columns": 3, "show_price": True, "show_duration": True,
                  "show_next_date": True, "show_seats": False, "per_person": True},
        "dashboard_color": "#5d6e4c",
        "dashboard_sidebar": "#1b2119",
        "texts": {"ar": {
            "online": "سارة متصلة الآن",
            "chatWith": "تحدّث مع سارة",
            "askCustom": "اطلب من سارة رحلة خاصة",
            "askNow": "اسأل سارة عن رحلتك",
            "bookWith": "احجز مع سارة",
            "howTitle": "سارة ترد خلال ثوانٍ.",
            "askAnything": "اسأل سارة أي شيء…",
            "how1Title": "تحدّث مع سارة",
            "how1Text": "على هذه الصفحة، بالعربي أو الإنجليزي، في أي ساعة. سارة تعرف كل رحلة وموعد وسعر.",
            "how2Text": "سارة تجمع مواعيدك وعدد المسافرين، ثم تعرض الإجمالي من نظام الحجز لدينا وتعطيك رقماً مرجعياً.",
            "welcome": WELCOME_AR.format(company=company_name),
        }},
    }).model_dump()


TRAINING = [
    ("What services do you offer besides trips?",
     "Besides tailor-made trips we offer private concierge services: VIP airport meet & assist, chauffeurs and "
     "luxury cars, yacht charters, private villas, restaurant and event bookings, and year-round lifestyle "
     "management. Tell me what you need and our team arranges it."),
    ("وش الخدمات اللي تقدمونها غير الرحلات؟",
     "غير الرحلات الخاصة نقدم خدمات كونسيرج: استقبال VIP في المطار، سائق خاص وسيارات فاخرة، يخوت، فلل خاصة، "
     "حجوزات مطاعم وفعاليات، وإدارة نمط الحياة طول السنة. قول لي وش تحتاج وفريقنا يرتب لك كل شيء."),
    ("Can you change the hotel or the itinerary?",
     "Of course. Every trip is tailor-made: we can change the hotel, room type, dates, add private guides or "
     "experiences. Tell me what you'd like and I'll pass it to your consultant with a new quote."),
    ("أقدر أغير الفندق أو البرنامج؟",
     "أكيد، كل رحلاتنا حسب الطلب: نغير الفندق أو نوع الغرفة أو التواريخ ونضيف مرشد خاص أو تجارب مميزة. "
     "قول لي وش تحب والمستشار يرسل لك عرض جديد."),
    ("Can you book me a chauffeur or a yacht?",
     "Yes, with pleasure. Tell me the city, the date and time, and how many guests, and our concierge team will "
     "confirm the options and price with you."),
    ("ابغى سائق خاص أو يخت، تقدرون؟",
     "أكيد وبكل سرور. عطني المدينة والتاريخ والوقت وعدد الضيوف، وفريق الكونسيرج يأكد لك الخيارات والسعر."),
    ("What is lifestyle management?",
     "It's a yearly membership: you get one personal concierge for travel, dining, events, gifts and everyday "
     "requests, with priority bookings. I'll ask the team to share the membership options with you."),
    ("How much is the deposit?",
     "A 30% deposit confirms your booking. The rest is due 21 days before departure."),
    ("كم العربون؟",
     "العربون 30% من قيمة الحجز ويثبت لك الحجز، والباقي قبل السفر بـ 21 يوماً."),
    ("Do the prices include flights?",
     "Yes, our packages include return business class flights from Muscat unless the package says otherwise. "
     "Economy or a private jet is possible on request."),
    ("هل السعر يشمل الطيران؟",
     "نعم، باقاتنا تشمل طيران درجة رجال الأعمال ذهاباً وإياباً من مسقط، وإذا تحب درجة سياحية أو طائرة خاصة نرتبها لك."),
    ("Where is your office?",
     "Our office is in Al Khuwair, Muscat, open Sunday to Thursday 8:30-17:30 and Saturday 10:00-14:00. Visits "
     "are by appointment, and I can book one for you."),
    ("What is your cancellation policy?",
     "Free cancellation up to 30 days before departure (minus 10 OMR per person fees), 50% from 29 to 15 days, "
     "and no refund within 14 days. You can change the date once for free up to 21 days before departure."),
    ("إذا ألغيت الحجز هل أسترجع فلوسي؟",
     "الإلغاء مجاني حتى 30 يوماً قبل السفر (مع خصم 10 ريالات رسوم للشخص)، و50% من 29 إلى 15 يوماً، "
     "وبعدها لا يوجد استرداد. وتقدر تغير التاريخ مرة وحدة مجاناً قبل 21 يوماً."),
    ("Do you arrange VIP airport service?",
     "Yes: meet & assist, fast track and lounge access at Muscat airport and most destinations, plus a chauffeur "
     "to your hotel. It's included in several of our trips and can be added to any booking."),
    ("تساعدوني في التأشيرة؟",
     "أكيد، نخلص لك التأشيرة كاملة. رسوم الخدمة 8 ريالات للشخص زائد رسوم السفارة."),
    ("How do I pay?",
     "By bank transfer, a secure card payment link (Visa, Mastercard or Amex), or at our office. Never share card "
     "numbers in the chat: your consultant sends you the payment details."),
    ("Can you plan a surprise for my wife?",
     "We'd love to. Anniversaries, proposals and birthdays are our favourite: flowers, a private dinner, a "
     "yacht at sunset... Tell me the date and the destination and our team will prepare a few ideas."),
]


PACKAGES: list[PackageDef] = [
    PackageDef(
        "salalah", "Salalah Khareef Private Retreat", "خريف صلالة الخاص", "Salalah", "Oman", 4, "395.000",
        "220.000", "Al Baleed Resort Salalah by Anantara", 5, 12, [], True,
        ["khareef", "family", "nature", "domestic", "private"], ["صلالة", "خريف", "ظفار", "عائلي", "خاص"],
        "Three nights in a private pool villa during the khareef: Wadi Darbat, Ain Razat and the Mughsail "
        "blowholes with a private 4x4 and guide, plus a picnic set up in the green mountains.",
        "ثلاث ليالٍ في فيلا بمسبح خاص أيام الخريف: وادي دربات وعين رزات ونوافير المغسيل بسيارة دفع رباعي "
        "ومرشد خاص، مع جلسة نزهة مجهزة في الجبال الخضراء.",
        ["Return flights Muscat-Salalah", "Pool villa with breakfast", "Private 4x4 and guide",
         "Mountain picnic set-up"],
        ["طيران مسقط - صلالة ذهاباً وإياباً", "فيلا بمسبح مع الإفطار", "سيارة ومرشد خاص", "جلسة نزهة في الجبل"],
        ["Lunches and dinners"], ["الغداء والعشاء"]),
    PackageDef(
        "dubai", "Dubai Family Luxury", "دبي الفاخرة للعائلة", "Dubai", "United Arab Emirates", 5, "695.000",
        "385.000", "Atlantis The Royal", 5, 12, [9, 23, 37, 51], True,
        ["family", "city", "shopping", "theme parks", "luxury"], ["دبي", "الامارات", "عائلي", "تسوق", "فاخر"],
        "Four nights at an iconic Palm Jumeirah resort with water park access, a private desert safari with "
        "dinner under the stars, Burj Khalifa at sunset and a private yacht cruise around the Palm.",
        "أربع ليالٍ في منتجع أيقوني على نخلة جميرا مع دخول الحديقة المائية، سفاري صحراوي خاص مع عشاء تحت "
        "النجوم، برج خليفة وقت الغروب ورحلة يخت خاصة حول النخلة.",
        ["Return business class flights", "4 nights with breakfast", "Private desert safari",
         "Private yacht 2 hours", "Chauffeur transfers"],
        ["طيران درجة رجال الأعمال", "4 ليالٍ مع الإفطار", "سفاري خاص", "يخت خاص ساعتين", "سائق خاص"],
        ["Lunches", "Personal expenses"], ["وجبات الغداء", "المصاريف الشخصية"]),
    PackageDef(
        "istanbul", "Istanbul & Cappadocia in Style", "إسطنبول وكبادوكيا بأسلوب فاخر", "Istanbul", "Turkey", 8,
        "1150.000", "690.000", "Çırağan Palace & Museum Hotel Cappadocia", 5, 10, [14, 35, 63], True,
        ["culture", "history", "balloon", "city", "luxury"], ["تركيا", "اسطنبول", "كبادوكيا", "تاريخ", "فاخر"],
        "Four nights in a palace on the Bosphorus with a private guide and a sunset yacht cruise, then three "
        "nights in a cave suite in Cappadocia with a private hot-air balloon flight at sunrise.",
        "أربع ليالٍ في قصر على البوسفور مع مرشد خاص ورحلة يخت عند الغروب، ثم ثلاث ليالٍ في جناح كهفي في "
        "كبادوكيا مع رحلة منطاد خاصة عند الشروق.",
        ["Business class + domestic flight", "7 nights with breakfast", "Private guide and car",
         "Private balloon flight", "Bosphorus yacht"],
        ["طيران رجال الأعمال وداخلي", "7 ليالٍ مع الإفطار", "مرشد وسيارة خاصة", "منطاد خاص", "يخت في البوسفور"],
        ["Turkey e-visa", "Dinners"], ["التأشيرة الإلكترونية", "العشاء"]),
    PackageDef(
        "georgia", "Georgia: Tbilisi & Kazbegi", "جورجيا: تبليسي وكازبيجي", "Tbilisi", "Georgia", 7, "845.000",
        "480.000", "The Biltmore Tbilisi & Rooms Kazbegi", 5, 10, [18, 46, 74], False,
        ["nature", "mountains", "family", "private"], ["جورجيا", "تبليسي", "كازبيجي", "طبيعة", "جبال"],
        "Four nights in Tbilisi and two nights facing Mount Kazbek, with a private car and an Arabic-speaking "
        "driver, a helicopter flight over the Caucasus and a private wine-country lunch in Kakheti.",
        "أربع ليالٍ في تبليسي وليلتان أمام جبل كازبيك، مع سيارة خاصة وسائق يتحدث العربية، رحلة هليكوبتر فوق "
        "القوقاز وغداء خاص في كاخيتي.",
        ["Return business class flights", "6 nights with breakfast", "Private car and driver",
         "Helicopter flight"],
        ["طيران درجة رجال الأعمال", "6 ليالٍ مع الإفطار", "سيارة خاصة مع سائق", "رحلة هليكوبتر"],
        ["Dinners"], ["العشاء"]),
    PackageDef(
        "maldives", "Maldives Private Island Honeymoon", "شهر عسل في جزيرة خاصة بالمالديف", "Malé", "Maldives", 6,
        "2450.000", None, "Soneva Jani Water Retreats", 5, 6, [12, 40, 68, 96], True,
        ["honeymoon", "beach", "luxury", "island"], ["المالديف", "شهر عسل", "شاطئ", "جزر", "فاخر"],
        "Five nights in an overwater retreat with a private pool and slide, a candle-lit dinner on a sandbank, a "
        "couples spa journey and a private snorkelling trip with a marine biologist.",
        "خمس ليالٍ في فيلا فوق الماء بمسبح خاص، عشاء على ضوء الشموع فوق جزيرة رملية، رحلة سبا للعرسان ورحلة "
        "غطس خاصة مع عالم أحياء بحرية.",
        ["Return business class flights", "Overwater villa, full board", "Speedboat or seaplane transfers",
         "Couples spa 90 min", "Sandbank dinner"],
        ["طيران درجة رجال الأعمال", "فيلا فوق الماء مع إقامة كاملة", "قارب سريع أو طائرة مائية",
         "سبا للعرسان 90 دقيقة", "عشاء على جزيرة رملية"],
        ["Travel insurance"], ["تأمين السفر"]),
    PackageDef(
        "umrah", "VIP Umrah", "عمرة VIP", "Makkah", "Saudi Arabia", 8, "1350.000", "890.000",
        "Raffles Makkah Palace & The Oberoi Madinah", 5, 16, [10, 31, 59], False,
        ["umrah", "religious", "family", "vip"], ["عمرة", "مكة", "المدينة", "السعودية"],
        "Five nights steps from the Haram in Makkah with a Kaaba-view suite and two nights in Madinah, with VIP "
        "airport service, private GMC transfers and a personal religious guide.",
        "خمس ليالٍ بجوار الحرم في مكة بجناح يطل على الكعبة وليلتان في المدينة المنورة، مع خدمة VIP في المطار، "
        "تنقلات خاصة بسيارة GMC ومرشد ديني خاص.",
        ["Return business class flights", "Umrah visa", "Kaaba-view suite with breakfast",
         "Private GMC transfers", "Personal religious guide"],
        ["طيران درجة رجال الأعمال", "تأشيرة العمرة", "جناح يطل على الكعبة مع الإفطار", "تنقلات خاصة GMC",
         "مرشد ديني خاص"],
        ["Lunches and dinners"], ["الغداء والعشاء"]),
    PackageDef(
        "zanzibar", "Zanzibar Barefoot Luxury", "زنجبار الفاخرة", "Zanzibar", "Tanzania", 7, "1190.000", "620.000",
        "The Residence Zanzibar", 5, 8, [25, 53, 81], False,
        ["beach", "island", "honeymoon", "relax", "luxury"], ["زنجبار", "تنزانيا", "شاطئ", "جزيرة", "شهر عسل"],
        "Six nights in a pool villa on a quiet beach, all-inclusive, with a private Stone Town tour, a dhow "
        "sunset cruise and a day on a private sandbank.",
        "ست ليالٍ في فيلا بمسبح على شاطئ هادئ بنظام شامل كلياً، مع جولة خاصة في ستون تاون، رحلة غروب بالداو "
        "ويوم على جزيرة رملية خاصة.",
        ["Return business class flights", "Pool villa, all-inclusive", "Private Stone Town tour",
         "Sunset dhow cruise"],
        ["طيران درجة رجال الأعمال", "فيلا بمسبح شاملة كلياً", "جولة خاصة في ستون تاون", "رحلة غروب بالداو"],
        ["Tanzania e-visa", "Travel insurance"], ["التأشيرة الإلكترونية", "تأمين السفر"]),
    PackageDef(
        "bali", "Bali Jungle & Ocean Villas", "بالي: فلل الغابة والمحيط", "Bali", "Indonesia", 9, "1290.000",
        "720.000", "Capella Ubud & Six Senses Uluwatu", 5, 8, [28, 56, 84], False,
        ["adventure", "beach", "nature", "honeymoon", "luxury"], ["بالي", "اندونيسيا", "مغامرة", "شاطئ", "شهر عسل"],
        "Tented villas in the Ubud jungle with private rafting and a sunrise trek on Mount Batur, then cliff-top "
        "ocean villas in Uluwatu with a private chef dinner.",
        "فلل خيام في غابات أوبود مع تجديف خاص وصعود جبل باتور عند الشروق، ثم فلل على المنحدرات المطلة على "
        "المحيط في أولواتو مع عشاء من طاهٍ خاص.",
        ["Return business class flights", "8 nights with breakfast", "Private rafting",
         "Mount Batur sunrise trek", "Private chef dinner"],
        ["طيران درجة رجال الأعمال", "8 ليالٍ مع الإفطار", "تجديف خاص", "صعود جبل باتور", "عشاء من طاهٍ خاص"],
        ["Visa on arrival fee"], ["رسوم التأشيرة عند الوصول"]),
    PackageDef(
        "cairo", "Cairo & a Private Nile Dahabiya", "القاهرة ورحلة نيلية خاصة", "Cairo", "Egypt", 8, "1050.000",
        "640.000", "Four Seasons Cairo & a private dahabiya", 5, 10, [15, 43, 71], False,
        ["history", "culture", "cruise", "family", "luxury"], ["مصر", "القاهرة", "النيل", "الأقصر", "تاريخ"],
        "A private after-hours visit to the Pyramids and the Grand Egyptian Museum, then four nights sailing "
        "from Luxor to Aswan on a private dahabiya with your own Egyptologist.",
        "زيارة خاصة للأهرامات والمتحف المصري الكبير، ثم أربع ليالٍ في رحلة نيلية من الأقصر إلى أسوان على مركب "
        "ذهبية خاص مع مرشد آثار خاص بك.",
        ["Return business class flights", "Hotel + full-board dahabiya", "Private Egyptologist",
         "All entrance fees"],
        ["طيران درجة رجال الأعمال", "فندق ومركب نيلي شامل الوجبات", "مرشد آثار خاص", "رسوم الدخول"],
        ["Egypt e-visa", "Tips"], ["التأشيرة", "الإكراميات"]),
    PackageDef(
        "baku", "Baku & Gabala Escape", "باكو وقبالا", "Baku", "Azerbaijan", 6, "760.000", "430.000",
        "Four Seasons Baku & Qafqaz Riverside", 5, 10, [16, 30, 58], False,
        ["city", "mountains", "family", "nature"], ["أذربيجان", "باكو", "قبالا", "جبال", "مدينة"],
        "Three nights on the Caspian boulevard in Baku and two nights in the Gabala mountains, with a private "
        "chauffeur, the Tufandag cable car and a private dinner in the Old City.",
        "ثلاث ليالٍ على كورنيش بحر قزوين في باكو وليلتان في جبال قبالا، مع سائق خاص، تلفريك توفانداغ وعشاء خاص "
        "في المدينة القديمة.",
        ["Return business class flights", "5 nights with breakfast", "Private chauffeur", "Gabala cable car"],
        ["طيران درجة رجال الأعمال", "5 ليالٍ مع الإفطار", "سائق خاص", "تلفريك قبالا"],
        ["Azerbaijan e-visa", "Dinners"], ["التأشيرة الإلكترونية", "العشاء"]),
    PackageDef(
        "thailand", "Thailand: Phuket Villas & Bangkok", "تايلاند: فلل بوكيت وبانكوك", "Phuket", "Thailand", 9,
        "1090.000", "560.000", "Amanpuri Phuket & The Peninsula Bangkok", 5, 10, [21, 49, 77], True,
        ["beach", "family", "city", "island", "luxury"], ["تايلاند", "بوكيت", "بانكوك", "شاطئ", "عائلي"],
        "Five nights in a pool villa in Phuket with a private yacht day to the Phi Phi islands, then three nights "
        "on the river in Bangkok with a private longtail boat tour.",
        "خمس ليالٍ في فيلا بمسبح في بوكيت مع يوم على يخت خاص إلى جزر في في، ثم ثلاث ليالٍ على النهر في بانكوك "
        "مع جولة خاصة بالقارب.",
        ["Business class + domestic flight", "8 nights with breakfast", "Private yacht day", "Chauffeur transfers"],
        ["طيران رجال الأعمال وداخلي", "8 ليالٍ مع الإفطار", "يوم على يخت خاص", "سائق خاص"],
        ["Lunches and dinners", "Travel insurance"], ["الغداء والعشاء", "تأمين السفر"]),
    PackageDef(
        "kerala", "Kerala Wellness Retreat", "كيرلا: رحلة استشفاء", "Kochi", "India", 7, "780.000", "420.000",
        "Kumarakom Lake Resort & a private houseboat", 5, 8, [19, 47, 75], False,
        ["wellness", "nature", "relax", "honeymoon", "ayurveda"], ["الهند", "كيرلا", "استرخاء", "طبيعة"],
        "The tea hills of Munnar, a night on a private luxury houseboat in the backwaters and four nights of "
        "personalised Ayurveda with a doctor's consultation at a lake resort.",
        "تلال الشاي في مونار، ليلة في قارب فاخر خاص، وأربع ليالٍ من علاجات الأيورفيدا المخصصة مع استشارة طبيب "
        "في منتجع على البحيرة.",
        ["Return business class flights", "6 nights, full board", "Private houseboat night",
         "Daily Ayurveda treatments"],
        ["طيران درجة رجال الأعمال", "6 ليالٍ إقامة كاملة", "ليلة في قارب خاص", "علاجات أيورفيدا يومية"],
        ["India e-visa"], ["التأشيرة الإلكترونية"]),
]
