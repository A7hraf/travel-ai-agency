"""A ready-made demo travel agency (Muscat, OMR) the platform owner creates in one click to present
the system: company, branding, AI persona and knowledge, staff logins, packages, trained answers
and, optionally, 30 days of sample chats and bookings so the dashboard, inbox and tickets look alive.

Everything is made in the caller's transaction (nothing is committed here). The staff passwords are
random, returned once to the caller and only stored as hashes; they are never logged.

Sample activity goes through the real AI tools (search, quote, booking) so tickets, seat holds,
quotes and chat cards have exactly the shape the live system makes; the times are then moved back
over the last 30 days. Sample customers are fictional: names only, "+968 9000 0xxx" numbers,
@example.com emails, and WhatsApp ids starting with "demo-" so no message can ever reach a real
phone (the demo company has no WhatsApp number connected either).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.agent import chat_cards
from ..ai.llm import ToolCall
from ..ai.tools import ToolContext, run_tool
from ..branding import Branding
from ..models import (
    Channel,
    Company,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageKind,
    Role,
    Sender,
    Ticket,
    TicketEvent,
    TicketStatus,
    TrainingExample,
    TravelPackage,
    User,
)
from ..schemas import UserCreate
from ..security import random_token, strong_password
from ..timeutil import local_today
from . import seats
from .users import create_company_user

log = logging.getLogger(__name__)

LANGUAGES = ("both", "en", "ar")
PROFILES = ("family", "luxury")  # family agency (default) or luxury travel & concierge brand
DEMO_MAX_USERS = 10

# --- Passwords --------------------------------------------------------------------------------





# --- Company content --------------------------------------------------------------------------

KNOWLEDGE = """\
OFFICE AND CONTACT
- Office: Al Khuwair, Way 3021, Muscat. Open Sunday to Thursday 8:30-17:30 and Saturday 10:00-14:00. Closed on Fridays.
- The AI consultant answers 24/7 on the website and WhatsApp; our team replies during office hours.
- All trips depart from Muscat International Airport (MCT) unless stated.

PRICES AND BOOKING
- Prices are in Omani rials (OMR), per person in a double room, flights included unless stated.
- Children 2-11 years pay the child price. Babies under 2 pay 10% of the adult price (no seat, no bed).
- A 30% deposit confirms the booking. The rest is due 21 days before departure.
- Bookings not paid within 48 hours give their seats back to other customers.
- Single room supplement: on request (usually 35-45% of the adult price).

PAYMENT METHODS
- Bank transfer (Bank Muscat or Bank Dhofar), a secure card payment link (Visa, Mastercard), or card/cash at our office.
- Instalments: bookings over 400 OMR can pay 30% now and the rest in two monthly payments.
- We never ask for card numbers in the chat.

CANCELLATION AND CHANGES
- Free cancellation up to 30 days before departure (the deposit is refunded minus 10 OMR per person fees).
- 29-15 days before departure: 50% of the total. 14 days or less: no refund.
- Umrah packages: deposit not refundable once the visa is issued.
- Changing the date is free once, up to 21 days before departure, subject to seats.

VISAS AND DOCUMENTS
- Passports must be valid for at least 6 months after return.
- Omani citizens: no visa needed for UAE, Georgia (up to 1 year), Azerbaijan e-visa on arrival rules may change,
  Turkey e-visa, Maldives visa on arrival, Thailand visa on arrival or exemption, Tanzania e-visa,
  Indonesia visa on arrival, Egypt e-visa, India e-visa. Our team confirms the current rules and applies for you.
- Visa service fee: 8 OMR per person (plus the embassy fee).
- Residents of Oman (non-Omani): visa rules depend on nationality; our consultant checks for you.

TRAVEL INSURANCE
- Recommended for every trip abroad. From 6 OMR per person per week, arranged by our team.
"""

KNOWLEDGE_AR = """\
معلومات بالعربية
- المكتب: الخوير، مسقط. من الأحد إلى الخميس 8:30 - 5:30 مساءً، والسبت 10 صباحاً - 2 ظهراً. الجمعة إجازة.
- الأسعار بالريال العماني للشخص في غرفة مزدوجة وتشمل الطيران من مسقط.
- عربون 30% يثبت الحجز، والباقي قبل المغادرة بـ 21 يوماً. الحجز غير المدفوع خلال 48 ساعة تعود مقاعده للبيع.
- طرق الدفع: تحويل بنكي (بنك مسقط أو بنك ظفار)، رابط دفع آمن بالبطاقة، أو في المكتب. التقسيط متاح للحجوزات فوق 400 ريال.
- الإلغاء: مجاني حتى 30 يوماً قبل المغادرة، 50% من 29 إلى 15 يوماً، ولا استرداد خلال 14 يوماً.
- التأشيرات: نساعد في كل التأشيرات (رسوم الخدمة 8 ريالات للشخص). الجواز صالح 6 أشهر على الأقل.
"""

INSTRUCTIONS = (
    "Mention the 30% deposit when the customer is ready to book. Suggest travel insurance for trips abroad. "
    "For groups of 10 or more, corporate trips or custom itineraries, hand over to the team."
)

WELCOME_EN = ("Hi! I'm Sara from {company} 👋 Tell me where you'd like to go, your dates and who is travelling, "
              "and I'll find the best trip for you.")
WELCOME_AR = ("أهلاً وسهلاً! معك سارة من {company} 👋 قول لي وين حاب تسافر، ومتى، وكم شخص، "
              "وأنا أختار لك أفضل رحلة.")

ABOUT_EN = ("{company} has been planning holidays for families in Oman since 2011: Umrah, honeymoons, family "
            "trips and weekends in Salalah. Our consultants in Al Khuwair know every hotel we sell, and Sara, "
            "our AI consultant, answers you any time of the day in Arabic or English.")
ABOUT_AR = ("منذ 2011 تنظم {company} رحلات العائلات في عُمان: العمرة، شهر العسل، الرحلات العائلية وعطلات "
            "صلالة. مستشارونا في الخوير يعرفون كل فندق نبيعه، وسارة، مستشارتنا الذكية، ترد عليك في أي وقت "
            "بالعربية أو الإنجليزية.")


def branding_for(company_name: str) -> dict:
    return Branding.model_validate({
        # "Desert" theme of the page editor: warm gold on the dark design.
        "primary_color": "#a8641f",
        "accent_color": "#e3b26b",
        "hero_style": "gradient",
        "hero_text_en": "Hand-picked trips from Muscat: Umrah, honeymoons, family holidays and Salalah weekends. "
                        "Ask Sara, she replies in seconds.",
        "hero_text_ar": "رحلات مختارة من مسقط: عمرة، شهر عسل، عطلات عائلية وعطلات صلالة. اسأل سارة، ترد عليك خلال ثوانٍ.",
        "about_title_en": f"About {company_name}"[:120],
        "about_title_ar": f"عن {company_name}"[:120],
        "about_en": ABOUT_EN.format(company=company_name),
        "about_ar": ABOUT_AR.format(company=company_name),
        "cards": {"style": "poster", "columns": 3, "show_price": True, "show_duration": True,
                  "show_next_date": True, "show_seats": True, "per_person": True},
        # The AI's name is "Sara" in one field: the Arabic page writes it in Arabic.
        "texts": {"ar": {
            "online": "سارة متصلة الآن",
            "chatWith": "تحدّث مع سارة",
            "askCustom": "اسأل سارة عن رحلة مخصّصة",
            "askNow": "اسأل سارة عن رحلتك",
            "bookWith": "احجز مع سارة",
            "howTitle": "سارة ترد خلال ثوانٍ.",
            "askAnything": "اسأل سارة أي شيء…",
            "how1Title": "تحدّث مع سارة",
            "how1Text": "على هذه الصفحة، بالعربي أو الإنجليزي، في أي ساعة. سارة تعرف كل باقة وموعد وسعر.",
            "how2Text": "سارة تجمع مواعيدك وعدد المسافرين، ثم تعرض الإجمالي من نظام الحجز لدينا وتعطيك رقماً مرجعياً.",
            "welcome": WELCOME_AR.format(company=company_name),
        }},
    }).model_dump()


TRAINING = [
    ("Can I pay in instalments?",
     "Yes. For bookings over 400 OMR you can pay a 30% deposit now and the rest in two monthly payments. "
     "Our consultant sets it up when they contact you."),
    ("هل أقدر أدفع بالتقسيط؟",
     "أكيد! للحجوزات فوق 400 ريال تدفع عربون 30% والباقي على دفعتين شهريتين. المستشار يرتب لك التفاصيل عند التواصل."),
    ("How much is the deposit?",
     "A 30% deposit confirms your booking. The rest is due 21 days before departure."),
    ("كم العربون؟",
     "العربون 30% من قيمة الحجز ويثبت لك المقاعد، والباقي قبل السفر بـ 21 يوماً."),
    ("Where is your office?",
     "Our office is in Al Khuwair, Muscat, open Sunday to Thursday 8:30-17:30 and Saturday 10:00-14:00."),
    ("وين مكتبكم؟",
     "مكتبنا في الخوير بمسقط، من الأحد للخميس 8:30 الصبح إلى 5:30 العصر، والسبت من 10 إلى 2 الظهر."),
    ("Do the prices include flights?",
     "Yes, all our packages include return flights from Muscat unless the package says otherwise."),
    ("هل السعر يشمل الطيران؟",
     "نعم، كل باقاتنا تشمل تذاكر الطيران ذهاباً وإياباً من مسقط إلا إذا ذُكر غير ذلك في الباقة."),
    ("What is your cancellation policy?",
     "Free cancellation up to 30 days before departure (minus 10 OMR per person fees), 50% from 29 to 15 days, "
     "and no refund within 14 days. You can change the date once for free up to 21 days before departure."),
    ("إذا ألغيت الحجز هل أسترجع فلوسي؟",
     "الإلغاء مجاني حتى 30 يوماً قبل السفر (مع خصم 10 ريالات رسوم للشخص)، و50% من 29 إلى 15 يوماً، "
     "وبعدها لا يوجد استرداد. وتقدر تغير التاريخ مرة وحدة مجاناً قبل 21 يوماً."),
    ("Do I need a visa?",
     "It depends on the destination and your nationality. Omani citizens need no visa for the UAE and Georgia, "
     "and get easy e-visas for Turkey, Egypt and India. Our team confirms the current rules and applies for you "
     "(8 OMR service fee per person)."),
    ("تساعدوني في التأشيرة؟",
     "أكيد، نخلص لك التأشيرة كاملة. رسوم الخدمة 8 ريالات للشخص زائد رسوم السفارة، والمستشار يأكد لك "
     "الشروط الحالية حسب جنسيتك."),
    ("How much do children pay?",
     "Children from 2 to 11 years pay the child price shown on the package. Babies under 2 pay 10% of the "
     "adult price (no seat, no bed)."),
    ("كم سعر الأطفال؟",
     "الأطفال من سنتين إلى 11 سنة لهم سعر الطفل الموجود في الباقة، والرضع تحت السنتين 10% من سعر البالغ."),
    ("Can you arrange a private trip for my company?",
     "Yes! We organise corporate trips and groups of 10 or more with special prices. I'll pass you to one of "
     "our consultants who will prepare an offer."),
    ("How do I pay?",
     "By bank transfer (Bank Muscat or Bank Dhofar), a secure card payment link, or at our office. "
     "Never share card numbers in the chat: our consultant sends you the payment details."),
    ("هل تقبلون الدفع بالبطاقة؟",
     "نعم، نرسل لك رابط دفع آمن بالبطاقة (فيزا أو ماستركارد)، أو تقدر تحول على بنك مسقط أو بنك ظفار، أو تدفع في المكتب."),
    ("Is travel insurance included?",
     "Travel insurance is not included, but we strongly recommend it. It starts from 6 OMR per person per week "
     "and our team can add it to your booking."),
]


# --- Packages ---------------------------------------------------------------------------------

def _khareef_dates(today: date) -> list[date]:
    """Weekly Thursdays of the next khareef season (mid July to end of August)."""
    year = today.year if today < date(today.year, 7, 1) else today.year + 1
    start = date(year, 7, 16)
    start += timedelta(days=(3 - start.weekday()) % 7)
    return [start + timedelta(weeks=w) for w in range(6)]


@dataclass
class PackageDef:
    key: str
    en: str
    ar: str
    destination: str
    country: str
    days: int
    price: str
    child: str | None
    hotel: str
    stars: int
    seats: int
    offsets: list[int]
    featured: bool
    tags_en: list[str]
    tags_ar: list[str]
    desc_en: str
    desc_ar: str
    inc_en: list[str]
    inc_ar: list[str]
    exc_en: list[str]
    exc_ar: list[str]


PACKAGES: list[PackageDef] = [
    PackageDef(
        "salalah", "Salalah Khareef Escape", "عطلة خريف صلالة", "Salalah", "Oman", 4, "145.000", "95.000",
        "Salalah Gardens Resort", 4, 30, [], True,
        ["khareef", "family", "nature", "domestic", "early booking"], ["صلالة", "خريف", "ظفار", "عائلي", "طبيعة"],
        "Three nights in green Salalah during the khareef monsoon: Ain Razat and Wadi Darbat, the Mughsail "
        "blowholes, Al Baleed and the frankincense souq, with a local driver-guide. Early booking for next season.",
        "ثلاث ليالٍ في صلالة الخضراء أيام الخريف: عين رزات ووادي دربات، نوافير المغسيل، البليد وسوق اللبان، "
        "مع سائق ومرشد محلي. حجز مبكر للموسم القادم.",
        ["Return flights Muscat-Salalah", "3 nights with breakfast", "Full-day guided tour", "Airport transfers"],
        ["طيران مسقط - صلالة ذهاباً وإياباً", "3 ليالٍ مع الإفطار", "جولة يوم كامل مع مرشد", "التوصيل من وإلى المطار"],
        ["Lunches and dinners"], ["الغداء والعشاء"]),
    PackageDef(
        "dubai", "Dubai Family Fun", "دبي للعائلة", "Dubai", "United Arab Emirates", 5, "265.000", "155.000",
        "Marina Family Resort", 4, 30, [9, 23, 37, 51], True,
        ["family", "city", "shopping", "theme parks"], ["دبي", "الامارات", "عائلي", "تسوق", "مدينة"],
        "Four nights in Dubai Marina with a desert safari and BBQ dinner, the Burj Khalifa observation deck, a "
        "full day at a theme park of your choice and a dhow dinner cruise.",
        "أربع ليالٍ في دبي مارينا مع رحلة سفاري وعشاء شواء، صعود برج خليفة، يوم كامل في مدينة ألعاب تختارها "
        "وعشاء في قارب الداو.",
        ["Return flights", "4 nights with breakfast", "Desert safari", "Burj Khalifa tickets", "Theme park day pass"],
        ["طيران ذهاباً وإياباً", "4 ليالٍ مع الإفطار", "رحلة سفاري", "تذاكر برج خليفة", "دخول مدينة ألعاب ليوم"],
        ["Lunches", "Personal expenses"], ["وجبات الغداء", "المصاريف الشخصية"]),
    PackageDef(
        "istanbul", "Istanbul & Cappadocia", "إسطنبول وكبادوكيا", "Istanbul", "Turkey", 8, "455.000", "325.000",
        "Sultanahmet Palace & Cave Suites", 4, 24, [14, 35, 63], True,
        ["culture", "family", "history", "balloon", "city"], ["تركيا", "اسطنبول", "كبادوكيا", "عائلي", "تاريخ"],
        "Four nights in Istanbul (Hagia Sophia, Blue Mosque, Bosphorus cruise, Grand Bazaar) and three nights in "
        "a cave hotel in Cappadocia with a sunrise hot-air balloon ride.",
        "أربع ليالٍ في إسطنبول (آيا صوفيا، الجامع الأزرق، رحلة البوسفور، البازار الكبير) وثلاث ليالٍ في فندق "
        "كهفي في كبادوكيا مع رحلة منطاد عند الشروق.",
        ["Return flights + domestic flight", "7 nights with breakfast", "Guided tours", "Hot-air balloon ride"],
        ["طيران دولي وداخلي", "7 ليالٍ مع الإفطار", "جولات مع مرشد", "رحلة المنطاد"],
        ["Turkey e-visa", "Lunches and dinners"], ["التأشيرة الإلكترونية", "الغداء والعشاء"]),
    PackageDef(
        "georgia", "Georgia: Tbilisi & Batumi", "جورجيا: تبليسي وباتومي", "Tbilisi", "Georgia", 7, "365.000",
        "260.000", "Old Town Tbilisi & Batumi Sea View", 4, 20, [18, 46, 74], False,
        ["nature", "mountains", "family"], ["جورجيا", "تبليسي", "باتومي", "طبيعة", "جبال"],
        "Three nights in Tbilisi with a day trip to the Kazbegi mountains, then three nights by the Black Sea in "
        "Batumi. Private car with an Arabic-speaking driver.",
        "ثلاث ليالٍ في تبليسي مع رحلة إلى جبال كازبيجي، ثم ثلاث ليالٍ على البحر الأسود في باتومي. سيارة خاصة "
        "مع سائق يتحدث العربية.",
        ["Return flights", "6 nights with breakfast", "Private car and driver", "Kazbegi day trip"],
        ["طيران ذهاباً وإياباً", "6 ليالٍ مع الإفطار", "سيارة خاصة مع سائق", "رحلة كازبيجي"],
        ["Lunches and dinners"], ["الغداء والعشاء"]),
    PackageDef(
        "maldives", "Maldives Honeymoon", "شهر عسل في المالديف", "Malé", "Maldives", 6, "945.000", None,
        "Coral Lagoon Water Villas", 5, 8, [12, 40, 68, 96], True,
        ["honeymoon", "beach", "luxury", "island"], ["المالديف", "شهر عسل", "شاطئ", "جزر"],
        "Five nights in an overwater villa with a private sunset dinner, a couples spa session and a snorkelling "
        "trip. Speedboat transfers from Malé airport.",
        "خمس ليالٍ في فيلا فوق الماء مع عشاء خاص عند الغروب، جلسة سبا للعرسان ورحلة غطس. التنقل بالقارب السريع "
        "من مطار ماليه.",
        ["Return flights", "Overwater villa, half board", "Speedboat transfers", "Couples spa 60 min",
         "Private sunset dinner"],
        ["طيران ذهاباً وإياباً", "فيلا فوق الماء مع نصف إقامة", "قارب سريع", "سبا للعرسان 60 دقيقة", "عشاء خاص"],
        ["Travel insurance", "Drinks outside meals"], ["تأمين السفر", "المشروبات خارج الوجبات"]),
    PackageDef(
        "umrah", "Umrah Premium", "عمرة مميزة", "Makkah", "Saudi Arabia", 10, "520.000", "390.000",
        "Haram View Hotel & Taibah Suites", 5, 40, [10, 31, 59], False,
        ["umrah", "religious", "family"], ["عمرة", "مكة", "المدينة", "السعودية"],
        "Six nights in Makkah within walking distance of the Haram and three nights in Madinah, with an "
        "experienced religious guide and Ziyarat tours.",
        "ست ليالٍ في مكة على مسافة قريبة من الحرم وثلاث ليالٍ في المدينة المنورة، مع مرشد ديني متمرس وجولات زيارات.",
        ["Return flights", "Umrah visa", "5-star hotels with breakfast", "Private bus", "Religious guide"],
        ["طيران ذهاباً وإياباً", "تأشيرة العمرة", "فنادق 5 نجوم مع الإفطار", "حافلة خاصة", "مرشد ديني"],
        ["Lunches and dinners"], ["الغداء والعشاء"]),
    PackageDef(
        "zanzibar", "Zanzibar Beach Retreat", "استرخاء في زنجبار", "Zanzibar", "Tanzania", 7, "495.000", "305.000",
        "Nungwi Palm Beach Resort", 4, 16, [25, 53, 81], False,
        ["beach", "island", "honeymoon", "relax"], ["زنجبار", "تنزانيا", "شاطئ", "جزيرة", "شهر عسل"],
        "Six nights all-inclusive on Nungwi beach with a Stone Town tour, a spice farm visit and a dhow sunset cruise.",
        "ست ليالٍ شاملة كلياً على شاطئ نونغوي مع جولة في ستون تاون، زيارة مزرعة التوابل ورحلة غروب بالداو.",
        ["Return flights", "All-inclusive resort", "Stone Town tour", "Sunset dhow cruise"],
        ["طيران ذهاباً وإياباً", "منتجع شامل كلياً", "جولة ستون تاون", "رحلة غروب بالداو"],
        ["Tanzania e-visa", "Travel insurance"], ["التأشيرة الإلكترونية", "تأمين السفر"]),
    PackageDef(
        "bali", "Bali Adventure & Beaches", "مغامرة بالي والشواطئ", "Bali", "Indonesia", 9, "535.000", "380.000",
        "Ubud Jungle Lodge & Seminyak Beach Hotel", 4, 16, [28, 56, 84], False,
        ["adventure", "beach", "nature", "honeymoon"], ["بالي", "اندونيسيا", "مغامرة", "شاطئ", "شهر عسل"],
        "Rice terraces, waterfalls and temples in Ubud, rafting and a sunrise trek on Mount Batur, then beach "
        "days in Seminyak.",
        "مدرجات الأرز والشلالات والمعابد في أوبود، تجديف في النهر وصعود جبل باتور عند الشروق، ثم أيام على شاطئ سيمينياك.",
        ["Return flights", "8 nights with breakfast", "Rafting", "Mount Batur sunrise trek"],
        ["طيران ذهاباً وإياباً", "8 ليالٍ مع الإفطار", "تجديف", "صعود جبل باتور"],
        ["Visa on arrival fee"], ["رسوم التأشيرة عند الوصول"]),
    PackageDef(
        "cairo", "Cairo & Nile Cruise", "القاهرة ورحلة النيل", "Cairo", "Egypt", 8, "405.000", "270.000",
        "Pyramids View Hotel & MS Nile Queen", 5, 26, [15, 43, 71], False,
        ["history", "culture", "cruise", "family"], ["مصر", "القاهرة", "النيل", "الأقصر", "تاريخ"],
        "The Pyramids of Giza and the Grand Egyptian Museum, then a four-night Nile cruise from Luxor to Aswan with "
        "Karnak, the Valley of the Kings and Abu Simbel.",
        "أهرامات الجيزة والمتحف المصري الكبير، ثم رحلة نيلية أربع ليالٍ من الأقصر إلى أسوان مع الكرنك ووادي "
        "الملوك وأبو سمبل.",
        ["Return flights", "Hotel + full-board cruise", "Egyptologist guide", "All entrance fees"],
        ["طيران ذهاباً وإياباً", "فندق ورحلة نيلية شاملة الوجبات", "مرشد آثار", "رسوم الدخول"],
        ["Egypt e-visa", "Tips"], ["التأشيرة", "الإكراميات"]),
    PackageDef(
        "baku", "Baku City & Mountains", "باكو: المدينة والجبال", "Baku", "Azerbaijan", 6, "315.000", "220.000",
        "Old City Boutique & Gabala Resort", 4, 20, [16, 30, 58], False,
        ["city", "mountains", "family", "nature"], ["أذربيجان", "باكو", "قبالا", "جبال", "مدينة"],
        "Three nights in Baku (Old City, Flame Towers, the Caspian boulevard) and two nights in the green "
        "mountains of Gabala with the cable car and Nohur lake.",
        "ثلاث ليالٍ في باكو (المدينة القديمة، أبراج اللهب، كورنيش بحر قزوين) وليلتان في جبال قبالا الخضراء مع "
        "التلفريك وبحيرة نوهور.",
        ["Return flights", "5 nights with breakfast", "Private transfers", "Gabala cable car"],
        ["طيران ذهاباً وإياباً", "5 ليالٍ مع الإفطار", "تنقلات خاصة", "تلفريك قبالا"],
        ["Azerbaijan e-visa", "Lunches and dinners"], ["التأشيرة الإلكترونية", "الغداء والعشاء"]),
    PackageDef(
        "thailand", "Thailand: Phuket & Bangkok", "تايلاند: بوكيت وبانكوك", "Phuket", "Thailand", 9, "425.000",
        "300.000", "Patong Bay Resort & Sukhumvit Hotel", 4, 20, [21, 49, 77], True,
        ["beach", "family", "city", "island"], ["تايلاند", "بوكيت", "بانكوك", "شاطئ", "عائلي"],
        "Five nights in Phuket with the Phi Phi islands speedboat tour, then three nights in Bangkok for the "
        "Grand Palace, floating markets and shopping.",
        "خمس ليالٍ في بوكيت مع جولة جزر في في بالقارب السريع، ثم ثلاث ليالٍ في بانكوك للقصر الكبير والأسواق "
        "العائمة والتسوق.",
        ["Return flights + domestic flight", "8 nights with breakfast", "Phi Phi islands tour", "Transfers"],
        ["طيران دولي وداخلي", "8 ليالٍ مع الإفطار", "جولة جزر في في", "التنقلات"],
        ["Lunches and dinners", "Travel insurance"], ["الغداء والعشاء", "تأمين السفر"]),
    PackageDef(
        "kerala", "Kerala Ayurveda & Backwaters", "كيرلا: الأيورفيدا والقوارب", "Kochi", "India", 7, "335.000",
        "235.000", "Kumarakom Lake Resort", 5, 14, [19, 47, 75], False,
        ["wellness", "nature", "relax", "honeymoon"], ["الهند", "كيرلا", "استرخاء", "طبيعة"],
        "Tea hills of Munnar, a night on a private houseboat in the Alleppey backwaters and three nights of "
        "Ayurveda treatments at a lake resort in Kumarakom.",
        "تلال الشاي في مونار، ليلة في قارب خاص في مياه أليبي، وثلاث ليالٍ من علاجات الأيورفيدا في منتجع على "
        "البحيرة في كوماراكوم.",
        ["Return flights", "6 nights, half board", "Private houseboat night", "3 Ayurveda sessions"],
        ["طيران ذهاباً وإياباً", "6 ليالٍ نصف إقامة", "ليلة في قارب خاص", "3 جلسات أيورفيدا"],
        ["India e-visa"], ["التأشيرة الإلكترونية"]),
]
PACKAGE_BY_KEY = {p.key: p for p in PACKAGES}


@dataclass(frozen=True)
class Profile:
    """The content of one kind of demo agency. All profiles use the same package keys (the sample chats need them)."""
    packages: list[PackageDef]
    knowledge: str
    instructions: str
    welcome_en: str
    welcome_ar: str
    training: list[tuple[str, str]]
    branding: object  # (company name) -> branding dict
    budget: int  # the "trips for N OMR per person" sample chat

    @property
    def by_key(self) -> dict[str, PackageDef]:
        return {p.key: p for p in self.packages}


def get_profile(name: str) -> Profile:
    if name == "luxury":
        from . import demo_luxury as lx  # noqa: PLC0415  (it imports PackageDef from here)

        return Profile(lx.PACKAGES, lx.KNOWLEDGE + "\n" + lx.KNOWLEDGE_AR, lx.INSTRUCTIONS, lx.WELCOME_EN,
                       lx.WELCOME_AR, lx.TRAINING, lx.branding_for, 900)
    return Profile(PACKAGES, KNOWLEDGE + "\n" + KNOWLEDGE_AR, INSTRUCTIONS, WELCOME_EN, WELCOME_AR, TRAINING,
                   branding_for, 300)


def _title(p: PackageDef, language: str) -> str:
    return {"en": p.en, "ar": p.ar}.get(language, f"{p.en} · {p.ar}")


def _both(en: list[str], ar: list[str], language: str) -> list[str]:
    if language == "en":
        return list(en)
    if language == "ar":
        return list(ar)
    return [f"{e} · {a}" for e, a in zip(en, ar)] + [a for a in ar[len(en):]]


def _departures(p: PackageDef, today: date) -> list[str]:
    days = _khareef_dates(today) if p.key == "salalah" else [today + timedelta(days=o) for o in p.offsets]
    return [d.isoformat() for d in days]


def _make_package(company: Company, p: PackageDef, language: str, today: date) -> TravelPackage:
    desc = {"en": p.desc_en, "ar": p.desc_ar}.get(language, f"{p.desc_en}\n\n{p.desc_ar}")
    tags = p.tags_en if language == "en" else p.tags_ar if language == "ar" else [*p.tags_en, *p.tags_ar]
    return TravelPackage(
        company_id=company.id, title=_title(p, language), destination=p.destination, country=p.country,
        description=desc, duration_days=p.days, price_per_person=Decimal(p.price),
        child_price=Decimal(p.child) if p.child else None, currency="OMR",
        departure_dates=_departures(p, today), includes=_both(p.inc_en, p.inc_ar, language),
        excludes=_both(p.exc_en, p.exc_ar, language), tags=[t.lower() for t in tags],
        hotel_name=p.hotel, hotel_stars=p.stars, seats_available=p.seats, is_active=True, is_featured=p.featured,
    )


# --- Staff ------------------------------------------------------------------------------------

STAFF = [
    # (key, role, full name, email local part, label)
    ("admin", Role.COMPANY_ADMIN, "Noor Al Hinai", "admin", "Company admin"),
    ("support1", Role.SUPPORT, "Khalid Al Amri", "khalid", "Support"),
    ("support2", Role.SUPPORT, "Aisha Al Lawati", "aisha", "Support"),
    ("tickets", Role.TICKET_AGENT, "Yousuf Al Habsi", "tickets", "Ticket employee"),
]


# --- Result -----------------------------------------------------------------------------------

@dataclass
class DemoLogin:
    role: str
    label: str
    full_name: str
    email: str
    password: str  # shown once to the platform owner, never stored


@dataclass
class DemoResult:
    company: Company
    logins: list[DemoLogin]
    counts: dict[str, int] = field(default_factory=dict)


def create_demo_company(db: Session, name: str, slug: str, admin_email: str | None = None,
                        language: str = "both", include_activity: bool = True,
                        today: date | None = None, profile: str = "family") -> DemoResult:
    """Build the whole demo agency in the caller's transaction (the caller commits).

    ``slug`` must already be valid and free (the router checks it like a normal company).
    """
    if language not in LANGUAGES:
        raise ValueError(f"language must be one of {LANGUAGES}")
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {PROFILES}")
    content = get_profile(profile)
    today = today or local_today()
    domain = f"{slug}.example"
    company = Company(
        name=name, slug=slug, max_users=DEMO_MAX_USERS, currency="OMR",
        contact_email=f"hello@{domain}", contact_phone="+968 2400 0000",
        ai_agent_name="Sara",
        ai_welcome_message=content.welcome_en.format(company=name),
        ai_welcome_message_ar=content.welcome_ar.format(company=name),
        ai_instructions=content.instructions,
        knowledge_base=content.knowledge,
        branding=content.branding(name),
    )
    db.add(company)
    db.flush()
    from .plans import ensure_subscription  # noqa: PLC0415

    ensure_subscription(db, company)  # the default plan, with the demo's account limit

    logins: list[DemoLogin] = []
    users: dict[str, User] = {}
    for key, role, full_name, local, label in STAFF:
        email = (admin_email if key == "admin" and admin_email else f"{local}@{domain}").lower()
        password = strong_password()
        user = create_company_user(db, company, UserCreate(email=email, full_name=full_name, password=password,
                                                           role=role), commit=False)
        users[key] = user
        logins.append(DemoLogin(role=str(role), label=label, full_name=full_name, email=email, password=password))

    packages: dict[str, TravelPackage] = {}
    for p in content.packages:
        pkg = _make_package(company, p, language, today)
        db.add(pkg)
        packages[p.key] = pkg
    for question, answer in content.training:
        db.add(TrainingExample(company_id=company.id, question=question, answer=answer))
    db.flush()

    if include_activity:
        _Activity(db, company, users, packages, language, today, content).build()
        db.flush()

    counts = {
        "users": len(users),
        "packages": len(packages),
        "training": len(content.training),
        "conversations": len(db.scalars(select(Conversation.id).where(Conversation.company_id == company.id)).all()),
        "tickets": len(db.scalars(select(Ticket.id).where(Ticket.company_id == company.id)).all()),
    }
    log.info("Demo company %s (%s) created: %s", company.id, slug, counts)
    return DemoResult(company=company, logins=logins, counts=counts)


# --- Sample activity --------------------------------------------------------------------------

CUSTOMERS = [
    # Fictional people (English and Arabic spelling), never a real customer.
    ("Salim Al Rawahi", "سالم الرواحي"), ("Fatma Al Busaidi", "فاطمة البوسعيدي"), ("Mohammed Al Kindi", "محمد الكندي"),
    ("Laila Al Saadi", "ليلى السعدي"), ("Hamad Al Maskari", "حمد المسكري"), ("Zainab Al Riyami", "زينب الريامي"),
    ("Omar Al Shukaili", "عمر الشكيلي"), ("Maryam Al Farsi", "مريم الفارسي"), ("Saif Al Mahrouqi", "سيف المحروقي"),
    ("Huda Al Jabri", "هدى الجابري"), ("Rashid Al Hosni", "راشد الحوسني"), ("Amal Al Kharusi", "أمل الخروصي"),
    ("Tariq Al Siyabi", "طارق السيابي"), ("Nasra Al Mamari", "نصرة المعمري"), ("Ali Al Wahaibi", "علي الوهيبي"),
    ("Sara Al Balushi", "سارة البلوشي"), ("Majid Al Ghafri", "ماجد الغافري"), ("Asma Al Rashdi", "أسماء الراشدي"),
    ("Badr Al Hadhrami", "بدر الحضرمي"), ("Shamsa Al Toubi", "شمسة التوبي"), ("Yaqoob Al Naabi", "يعقوب النعبي"),
    ("Ruqaya Al Shidi", "رقية الشيدي"), ("Khalfan Al Abri", "خلفان العبري"), ("Muna Al Hashmi", "منى الهاشمي"),
    ("Ibrahim Al Kalbani", "إبراهيم الكلباني"), ("Thuraya Al Mukhaini", "ثريا المخيني"), ("Nasser Al Yahyai", "ناصر اليحيائي"),
    ("Ahlam Al Sinani", "أحلام السناني"), ("Hilal Al Mawali", "هلال المعولي"), ("Wafa Al Zakwani", "وفاء الذكواني"),
    ("Sultan Al Ismaili", "سلطان الإسماعيلي"), ("Iman Al Barwani", "إيمان البرواني"), ("Juma Al Harrasi", "جمعة الحراصي"),
    ("Rahma Al Ruqaishi", "رحمة الرقيشي"), ("Said Al Qasmi", "سعيد القاسمي"), ("Ghalia Al Nadabi", "غالية الندابي"),
]

AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر",
             "ديسمبر"]
EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _date_text(iso: str, lang: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {(AR_MONTHS if lang == 'ar' else EN_MONTHS)[d.month - 1]} {d.year}"


def _omr(value, lang: str) -> str:
    amount = f"{float(value):,.3f}"
    return f"{amount} ر.ع." if lang == "ar" else f"{amount} OMR"


def _pax(adults: int, children: int, lang: str) -> str:
    if lang == "ar":
        a = {1: "بالغ واحد", 2: "بالغان"}.get(adults, f"{adults} بالغين")
        c = {0: "", 1: "طفل واحد", 2: "طفلان"}.get(children, f"{children} أطفال")
        return f"{a} و{c}" if c else a
    a = "1 adult" if adults == 1 else f"{adults} adults"
    c = "" if not children else "1 child" if children == 1 else f"{children} children"
    return f"{a}, {c}" if c else a


@dataclass
class BookingPlan:
    pkg: str
    date_index: int
    adults: int
    children: int
    status: str
    lang: str
    channel: str
    days_ago: float
    ask: tuple[str, str]  # (english, arabic) first message of the customer
    query: str
    payment_ref: str | None = None
    released: bool = False  # unpaid for more than the hold time: its seats went back on sale
    note: str = ""


BOOKINGS: list[BookingPlan] = [
    BookingPlan("salalah", 2, 2, 2, TicketStatus.CONFIRMED, "ar", Channel.WEB, 27.2,
                ("We want Salalah in the khareef with the kids", "نبغى صلالة في الخريف مع الأولاد، عندكم باقات؟"),
                "Salalah khareef family", "BM-TRF-48213", note="Early booking, wants a ground-floor room."),
    BookingPlan("dubai", 1, 2, 2, TicketStatus.CONFIRMED, "ar", Channel.WHATSAPP, 24.4,
                ("Family trip to Dubai?", "السلام عليكم، ابغى رحلة دبي للعائلة، عندي ولدين"),
                "Dubai family", "CARD-77310"),
    BookingPlan("maldives", 0, 2, 0, TicketStatus.CONFIRMED, "en", Channel.WEB, 21.6,
                ("Hi! We're getting married next month and looking for a honeymoon in the Maldives 💍",
                 "مرحبا، ابغى شهر عسل في المالديف"),
                "Maldives honeymoon", "BD-TRF-90412", note="Honeymoon cake and flower decoration requested."),
    BookingPlan("kerala", 0, 2, 0, TicketStatus.CONFIRMED, "en", Channel.WHATSAPP, 18.3,
                ("Hello, do you have something relaxing like Ayurveda in Kerala for my parents?",
                 "عندكم رحلة استرخاء في كيرلا؟"),
                "Kerala ayurveda", "OFFICE-CASH-2291"),
    BookingPlan("istanbul", 0, 2, 0, TicketStatus.PAID, "en", Channel.WEB, 11.5,
                ("Looking for Istanbul and Cappadocia for two, with the balloon ride", "إسطنبول وكبادوكيا لشخصين"),
                "Istanbul Cappadocia", "BM-TRF-51877"),
    BookingPlan("georgia", 1, 2, 1, TicketStatus.PAID, "ar", Channel.WHATSAPP, 9.2,
                ("Georgia with family", "مرحبا، كم سعر رحلة جورجيا؟ نحن شخصين وطفل"),
                "Georgia Tbilisi family", "CARD-66402"),
    BookingPlan("umrah", 0, 4, 0, TicketStatus.IN_PROGRESS, "ar", Channel.WHATSAPP, 4.3,
                ("Umrah for my parents", "السلام عليكم، ابغى أحجز عمرة لي ولوالدي ووالدتي وزوجتي"),
                "Umrah"),
    BookingPlan("maldives", 0, 2, 0, TicketStatus.IN_PROGRESS, "ar", Channel.WHATSAPP, 2.4,
                ("Maldives honeymoon", "مساء الخير، نبغى شهر عسل في المالديف الشهر الجاي"),
                "Maldives honeymoon"),
    BookingPlan("thailand", 0, 2, 1, TicketStatus.IN_PROGRESS, "en", Channel.WEB, 3.1,
                ("Any beach holiday in Thailand for a family with one kid?", "تايلاند للعائلة"),
                "Thailand family beach"),
    BookingPlan("maldives", 0, 2, 0, TicketStatus.PENDING_PAYMENT, "en", Channel.WEB, 0.6,
                ("Do you still have the Maldives overwater villas this month?", "المالديف هذا الشهر؟"),
                "Maldives honeymoon"),
    BookingPlan("zanzibar", 0, 2, 0, TicketStatus.PENDING_PAYMENT, "en", Channel.WEB, 0.35,
                ("Something all-inclusive on a beach, maybe Zanzibar?", "زنجبار"),
                "Zanzibar beach"),
    BookingPlan("baku", 1, 2, 2, TicketStatus.PENDING_PAYMENT, "ar", Channel.WEB, 4.8,
                ("Baku with the family", "كم سعر باكو للعائلة؟ شخصين وطفلين"),
                "Baku family", released=True),
    BookingPlan("bali", 0, 2, 0, TicketStatus.CANCELLED, "en", Channel.WEB, 16.4,
                ("Bali for two adventurous people?", "بالي لشخصين"), "Bali adventure",
                note="Customer's leave was not approved."),
    BookingPlan("cairo", 0, 3, 0, TicketStatus.CANCELLED, "ar", Channel.WHATSAPP, 13.7,
                ("Cairo and the Nile cruise", "عندكم رحلة القاهرة والنيل؟ ثلاث أشخاص"), "Cairo Nile",
                "BM-TRF-60218", note="Booked another date by phone."),
]

# AI-only chats: (lang, channel, days ago, closed?, customer text, search query or None, AI answer if no search,
# follow-up customer text, follow-up AI answer)
INFO_CHATS = [
    ("ar", Channel.WEB, 0.15, False, "ابغى رحلة شهر عسل في ديسمبر، الميزانية حوالي ألف ريال للشخص", "honeymoon", None,
     "المالديف تشمل الطيران؟", "نعم، كل باقاتنا تشمل الطيران ذهاباً وإياباً من مسقط، والمالديف تشمل أيضاً القارب السريع من المطار."),
    ("en", Channel.WHATSAPP, 0.4, False, "Hi, what's your office address?", None,
     "Our office is in Al Khuwair, Muscat, open Sunday to Thursday 8:30-17:30 and Saturday 10:00-14:00. "
     "You can also book everything right here with me 😊", None, None),
    ("ar", Channel.WHATSAPP, 1.2, False, "عندكم رحلات عائلية بميزانية {budget} ريال للشخص؟",
     {"query": "family", "max_price_per_person": "{budget}"}, None,
     "والأطفال كم سعرهم؟", "الأطفال من سنتين إلى 11 سنة لهم سعر الطفل في الباقة، مثلاً {dubai_ar} {dubai_child} ريال للطفل."),
    ("en", Channel.WEB, 1.9, False, "Do I need a visa for Georgia? I have an Omani passport", None,
     "Good news: Omani citizens don't need a visa for Georgia (stays up to 1 year). Your passport must be valid for "
     "at least 6 months. Would you like to see our Georgia trip?", "Yes please",
     "{georgia_en} is {georgia_days} days from {georgia_price} OMR per person, with a private car and an Arabic-speaking "
     "driver. The next departures have seats left. Shall I check a date for you?"),
    ("ar", Channel.WEB, 2.7, True, "كم العربون عشان أثبت الحجز؟", None,
     "العربون 30% من قيمة الحجز ويثبت لك المقاعد، والباقي قبل السفر بـ 21 يوماً. تحب أساعدك تختار رحلة؟", None, None),
    ("en", Channel.WEB, 3.6, True, "Istanbul in winter, is it a good idea with kids?", "Istanbul family", None,
     "How cold is it in December?", "Istanbul is around 6-12°C in December, so warm jackets are a must, and "
     "Cappadocia can see snow, which kids usually love ❄️"),
    ("ar", Channel.WHATSAPP, 5.2, True, "متى مواعيد العمرة الجاية؟", "Umrah", None, None, None),
    ("en", Channel.WHATSAPP, 6.1, True, "Can I cancel if my plans change?", None,
     "Yes: cancellation is free up to 30 days before departure (minus 10 OMR per person fees), 50% from 29 to 15 "
     "days, and no refund within 14 days. You can also change the date once for free up to 21 days before.",
     None, None),
    ("en", Channel.WEB, 7.4, True, "Thailand with two kids aged 5 and 8, what do you have?", "Thailand family", None,
     None, None),
    ("ar", Channel.WEB, 8.8, True, "ابغى أشوف الأهرامات، كم سعر رحلة مصر؟", "Cairo Egypt", None, None, None),
    ("ar", Channel.WHATSAPP, 10.5, True, "باكو حلوة في الشتاء؟", "Baku", None,
     "يعني فيها ثلج؟", "في الشتاء تنزل الحرارة في قبالا وقد ينزل الثلج على الجبال، والمدينة باكو باردة وجميلة بالأضواء ✨"),
    ("en", Channel.WEB, 12.9, True, "Do you accept card payments?", None,
     "Yes: our consultant sends you a secure card payment link (Visa or Mastercard), or you can pay by bank transfer "
     "or at our office. Please never share card numbers in the chat.", None, None),
    ("en", Channel.WEB, 15.2, True, "Kerala or Bali for a quiet honeymoon?", "honeymoon", None, None, None),
    ("ar", Channel.WEB, 19.6, True, "عندكم رحلات لصلالة؟", "Salalah", None, None, None),
    ("en", Channel.WHATSAPP, 23.1, True, "Is travel insurance included?", None,
     "Travel insurance isn't included, but we recommend it for every trip abroad. It starts from 6 OMR per person "
     "per week and our team can add it to your booking.", None, None),
    ("ar", Channel.WEB, 28.3, True, "زنجبار تحتاج تأشيرة؟", None,
     "زنجبار تحتاج تأشيرة إلكترونية لتنزانيا، وفريقنا يخلصها لك (رسوم الخدمة 8 ريالات للشخص). تحب أعرض لك باقة "
     "استرخاء في زنجبار؟", None, None),
]

# Chats handed to the team without a booking:
# (lang, channel, days ago, staff key or None (waiting), end status, customer text, reason, staff reply, customer reply)
HANDOVER_CHATS = [
    ("ar", Channel.WHATSAPP, 0.12, None, ConversationStatus.HUMAN,
     "ابغى أكلم موظف لو سمحت، عندي استفسار عن رحلة لشركتنا 25 موظف", "Corporate trip for 25 employees", None, None),
    ("en", Channel.WEB, 0.05, None, ConversationStatus.HUMAN,
     "Can I talk to a person? I need a Schengen visa appointment for my mother", "Schengen visa appointment",
     None, None),
    ("ar", Channel.WEB, 0.9, "support2", ConversationStatus.HUMAN,
     "نبغى شهر عسل في سيشل، ما لقيتها عندكم، ممكن موظف يساعدنا؟", "Custom honeymoon to Seychelles",
     "أهلاً وسهلاً! معك عائشة من الفريق 🌴 أجهز لكم عرض سيشل 6 ليالٍ وأرسله لكم اليوم. أي فندق تفضلون، على الشاطئ أو فيلا مع مسبح؟",
     "فيلا مع مسبح لو سمحتي"),
    ("en", Channel.WHATSAPP, 6.5, "support1", ConversationStatus.CLOSED,
     "I booked with you last year and want to complain, the hotel transfer was late", "Complaint about a transfer",
     "Hello, this is Khalid from the team. I'm very sorry about the late transfer. I've added a note to your file "
     "and we've arranged a free airport upgrade for your next trip.", "Thank you Khalid, appreciated"),
    ("ar", Channel.WEB, 11.2, "support1", ConversationStatus.AI,
     "أبغى أغير تاريخ رحلتي، أكلم موظف؟", "Change of travel date",
     "أهلاً، معك خالد. غيرت لك التاريخ بنجاح وأرسلت لك التأكيد على الإيميل. إذا عندك أي سؤال ثاني سارة تساعدك 🙂",
     "تمام، مشكور"),
]

SEARCH_INTRO = {
    "en": "Here are some trips you may like:",
    "ar": "عندنا لكم هذي الرحلات:",
}
SEARCH_OUTRO = {"en": "Which one would you like? I can check dates and prices for you.",
                "ar": "أي وحدة تعجبكم؟ أقدر أشيك لكم التواريخ والأسعار."}


class _Activity:
    """30 days of sample chats and bookings, made through the real AI tools."""

    def __init__(self, db: Session, company: Company, users: dict[str, User], packages: dict[str, TravelPackage],
                 language: str, today: date, content: Profile | None = None):
        self.db, self.company, self.users, self.packages = db, company, users, packages
        self.content = content or get_profile("family")
        self.language, self.today = language, today
        self.now = datetime.now(timezone.utc)
        self.customer_no = 0
        self.call_no = 0

    # -- helpers --

    def _customer(self, channel: str, lang: str) -> Customer:
        name_en, name_ar = CUSTOMERS[self.customer_no % len(CUSTOMERS)]
        self.customer_no += 1
        name = name_ar if lang == "ar" else name_en
        number = f"9000{100 + self.customer_no:04d}"  # +968 9000 0101... clearly not a real number
        first = name_en.split()[0].lower()
        return Customer(
            company_id=self.company.id, name=name, phone=f"+968 {number[:4]} {number[4:]}",
            email=f"{first}.{self.customer_no}@example.com" if channel == Channel.WEB else None,
            whatsapp_id=f"demo-968{number}" if channel == Channel.WHATSAPP else None,
        )

    def _conversation(self, channel: str, start: datetime, lang: str) -> tuple[Conversation, Customer]:
        customer = self._customer(channel, lang)
        customer.created_at = start
        self.db.add(customer)
        self.db.flush()
        conv = Conversation(company_id=self.company.id, customer_id=customer.id, channel=channel,
                            status=ConversationStatus.AI, created_at=start, last_message_at=start,
                            ai_started_at=start, public_token=random_token() if channel == Channel.WEB else None)
        self.db.add(conv)
        self.db.flush()
        return conv, customer

    def _add(self, conv: Conversation, sender: str, content: str, at: datetime, kind: str = MessageKind.TEXT,
             meta: dict | None = None, author: User | None = None) -> Message:
        msg = Message(conversation_id=conv.id, sender=sender, kind=kind, content=content, meta=meta,
                      author_user_id=author.id if author else None, created_at=at)
        if conv.channel == Channel.WHATSAPP and kind == MessageKind.TEXT and sender in (Sender.AI, Sender.AGENT):
            msg.delivery_status = "read"
        self.db.add(msg)
        if kind == MessageKind.TEXT and sender != Sender.SYSTEM:
            conv.last_message_at = max(conv.last_message_at, at)
        if sender == Sender.CUSTOMER:
            conv.last_customer_message_at = at
        return msg

    def _stamp(self, at: datetime) -> None:
        """Times of the rows the AI tools just added (handover notes, ticket history)."""
        for obj in list(self.db.new):
            if isinstance(obj, (Message, TicketEvent)) and obj.created_at is None:
                obj.created_at = at

    def _ctx(self, conv: Conversation, customer: Customer) -> ToolContext:
        return ToolContext(db=self.db, company=self.company, conversation=conv, customer=customer, today=self.today)

    def _tool(self, ctx: ToolContext, conv: Conversation, name: str, args: dict, at: datetime) -> dict:
        """One tool call of the AI, stored like the live agent stores it."""
        self.call_no += 1
        call = ToolCall(f"call_demo{self.call_no:04d}", name, args).to_openai()
        self._add(conv, Sender.AI, "", at, MessageKind.TOOL_CALL, {"tool_calls": [call]})
        result = run_tool(ctx, name, args)
        self._stamp(at)
        self._add(conv, Sender.AI, json.dumps(result, ensure_ascii=False, default=str, separators=(",", ":")),
                  at, MessageKind.TOOL_RESULT, {"tool_call_id": call["id"], "name": name})
        return result

    def _reply(self, conv: Conversation, text: str, at: datetime, results: list[tuple[str, dict]]) -> Message:
        cards = chat_cards(results, text)
        return self._add(conv, Sender.AI, text, at, meta={"cards": cards} if cards else None)

    def _title(self, key: str, lang: str) -> str:
        p = self.content.by_key[key]
        return p.ar if lang == "ar" else p.en

    def _list_text(self, results: dict, lang: str) -> str:
        items = results.get("results") or results.get("alternatives") or []
        lines = []
        for item in items[:3]:
            title = item["title"]  # the AI quotes the catalogue as the tools return it
            days = f"{item['duration_days']} أيام" if lang == "ar" else f"{item['duration_days']} days"
            lines.append(f"• {title} – {days} – {_omr(item['price_per_person'], lang)}")
        return "\n".join([SEARCH_INTRO[lang], *lines, SEARCH_OUTRO[lang]])

    @staticmethod
    def _gap(at: datetime, minutes: float) -> datetime:
        return at + timedelta(minutes=minutes)

    def _event(self, ticket: Ticket, user: User | None, action: str, at: datetime, old=None, new=None) -> None:
        self.db.add(TicketEvent(ticket_id=ticket.id, user_id=user.id if user else None,
                                actor=user.full_name if user else "System", action=action,
                                old_value=None if old is None else str(old), new_value=None if new is None else str(new),
                                created_at=at))

    def _status(self, ticket: Ticket, conv: Conversation, user: User, new: str, at: datetime) -> None:
        """Same history and chat note as an employee changing the status on the Tickets page."""
        old = ticket.status
        self._event(ticket, user, "status", at, old, new)
        self._add(conv, Sender.SYSTEM, f"Ticket {ticket.reference}: {old} → {new} by {user.full_name}", at)
        ticket.status = new
        ticket.updated_at = at
        if new == TicketStatus.IN_PROGRESS and ticket.assigned_to_id is None:
            ticket.assigned_to_id = user.id

    # -- build --

    def build(self) -> None:
        for plan in BOOKINGS:
            self._booking(plan)
        for chat in INFO_CHATS:
            self._info(*chat)
        for chat in HANDOVER_CHATS:
            self._handover(*chat)
        # Unpaid bookings older than the hold time give their seats back, exactly like the live system;
        # the release is dated when the hold ran out.
        self.db.flush()
        seats.release_expired(self.db, company_id=self.company.id)
        for obj in list(self.db.new):
            if isinstance(obj, TicketEvent) and obj.action == seats.RELEASED_ACTION and obj.created_at is None:
                ticket = self.db.get(Ticket, obj.ticket_id)
                obj.created_at = (ticket.seats_held_at or ticket.created_at) + timedelta(hours=seats.hold_hours())

    def _booking(self, plan: BookingPlan) -> None:
        lang, db = plan.lang, self.db
        pkg = self.packages[plan.pkg]
        dep = pkg.departure_dates[plan.date_index]
        start = self.now - timedelta(days=plan.days_ago)
        conv, customer = self._conversation(plan.channel, start, lang)
        ctx = self._ctx(conv, customer)
        results: list[tuple[str, dict]] = []

        t = start
        self._add(conv, Sender.CUSTOMER, plan.ask[1] if lang == "ar" else plan.ask[0], t)
        t = self._gap(t, 0.4)
        found = self._tool(ctx, conv, "search_packages", {"query": plan.query}, t)
        self._reply(conv, self._list_text(found, lang), t, [("search_packages", found)])

        t = self._gap(t, 2.5)
        title = self._title(plan.pkg, lang)
        pax = _pax(plan.adults, plan.children, lang)
        when = _date_text(dep, lang)
        self._add(conv, Sender.CUSTOMER,
                  f"{title} حلوة! ممكن تشيكين لنا {when}؟ نحن {pax}" if lang == "ar"
                  else f"{title} sounds great. Can you check {when} for {pax}?", t)
        t = self._gap(t, 0.5)
        args = {"package_id": pkg.id, "departure_date": dep, "adults": plan.adults, "children": plan.children}
        quote = self._tool(ctx, conv, "quote_booking", args, t)
        if "total_price" not in quote:
            raise RuntimeError(f"Demo quote failed for {plan.pkg}: {quote}")
        total = _omr(quote["total_price"], lang)
        summary = (f"ملخص الحجز:\n• {pkg.title}\n• المغادرة: {when}\n• {pax}\n• الإجمالي: {total}\n"
                   "العربون 30% يثبت الحجز. أأكد لكم الحجز؟" if lang == "ar" else
                   f"Here is your booking summary:\n• {pkg.title}\n• Departure: {when}\n• {pax}\n• Total: {total}\n"
                   "A 30% deposit confirms it. Shall I go ahead?")
        self._reply(conv, summary, t, [("quote_booking", quote)])

        t = self._gap(t, 3)
        number = customer.phone
        self._add(conv, Sender.CUSTOMER,
                  f"إيه أكدي الحجز. الاسم {customer.name}، الرقم {number}" if lang == "ar"
                  else f"Yes please, book it. Name: {customer.name}, phone {number}", t)
        t = self._gap(t, 0.5)
        booked = self._tool(ctx, conv, "create_booking_ticket", {
            **args, "lead_traveler_name": customer.name, "contact_phone": number,
            "contact_email": customer.email or "", "special_requests": plan.note}, t)
        ref = booked.get("ticket_reference")
        if not ref:
            raise RuntimeError(f"Demo booking failed for {plan.pkg}: {booked}")
        results.append(("create_booking_ticket", booked))
        self._reply(conv, (f"تم! رقم الحجز {ref} 🎉 سيتواصل معكم أحد مستشاري {self.company.name} قريباً لإتمام "
                           "دفع العربون." if lang == "ar" else
                           f"Done! Your booking reference is {ref} 🎉 A {self.company.name} consultant will contact "
                           "you shortly to complete the 30% deposit."), t, results)

        ticket = db.scalar(select(Ticket).where(Ticket.reference == ref))
        ticket.created_at = ticket.updated_at = t
        ticket.seats_held_at = t
        ticket.internal_notes = ""
        self._staff_steps(plan, ticket, conv, t)
        db.flush()  # the next bookings count seats from the database (the session does not autoflush)

    def _staff_steps(self, plan: BookingPlan, ticket: Ticket, conv: Conversation, t: datetime) -> None:
        lang = plan.lang
        if plan.status == TicketStatus.PENDING_PAYMENT:
            return  # waiting for the team (or its hold ran out: released in build())
        agent = self.users["tickets"]
        first = ticket.lead_traveler_name.split()[0]
        deposit = _omr((ticket.total_price * Decimal("0.3")).quantize(Decimal("0.001")), lang)

        if plan.status == TicketStatus.CANCELLED and plan.days_ago > 15:
            # Cancelled by the customer before anybody called them.
            t = self._gap(t, 95)
            self._add(conv, Sender.CUSTOMER, "آسف، لازم ألغي، ما وافقوا على إجازتي 😔" if lang == "ar"
                      else "Sorry, I need to cancel, my leave was not approved 😔", t)
            t = self._gap(t, 40)
            conv.assigned_to_id = agent.id
            self._add(conv, Sender.AGENT, f"ولا يهمك {first}، ألغيت الحجز {ticket.reference}. نشوفك قريباً!"
                      if lang == "ar" else f"No problem {first}, I've cancelled booking {ticket.reference}. "
                                           "We hope to see you soon!", t, author=agent)
            self._cancel(ticket, conv, agent, t)
            return

        # A ticket employee picks it up and sends the payment details.
        t = self._gap(t, 35)
        self._status(ticket, conv, agent, TicketStatus.IN_PROGRESS, t)
        conv.assigned_to_id = agent.id
        conv.status = ConversationStatus.HUMAN
        t = self._gap(t, 2)
        self._add(conv, Sender.AGENT,
                  f"أهلاً {first}، معك يوسف من {self.company.name}. أرسلت لك رابط الدفع الآمن للعربون ({deposit}). "
                  "إذا تفضل التحويل البنكي أرسل لك تفاصيل الحساب." if lang == "ar" else
                  f"Hello {first}, this is Yousuf from {self.company.name}. I've sent you the secure payment link for "
                  f"the 30% deposit ({deposit}). Bank transfer is fine too.", t, author=agent)
        if plan.status == TicketStatus.IN_PROGRESS:
            ticket.internal_notes = "Payment link sent, waiting for the customer."
            self._event(ticket, agent, "notes", self._gap(t, 1))
            return

        t = self._gap(t, 180)
        self._add(conv, Sender.CUSTOMER, "تم التحويل، مشكورين 🙏" if lang == "ar" else "Paid, thank you! 🙏", t)
        t = self._gap(t, 20)
        self._event(ticket, agent, "payment_reference", t, None, plan.payment_ref)
        ticket.payment_reference = plan.payment_ref
        if plan.status == TicketStatus.CANCELLED:
            # Paid, then cancelled on request (refund handled outside the system).
            self._status(ticket, conv, agent, TicketStatus.PAID, t)
            t = self._gap(t, 60 * 24)
            self._add(conv, Sender.CUSTOMER, "للأسف نبغى نلغي، حجزنا تاريخ ثاني بالتلفون" if lang == "ar"
                      else "Unfortunately we need to cancel.", t)
            t = self._gap(t, 30)
            self._add(conv, Sender.AGENT, f"تم إلغاء الحجز {ticket.reference} وسيتم استرداد المبلغ حسب سياسة الإلغاء."
                      if lang == "ar" else f"Booking {ticket.reference} is cancelled; the refund follows our policy.",
                      t, author=agent)
            self._cancel(ticket, conv, agent, t)
            return

        self._status(ticket, conv, agent, TicketStatus.PAID, t)
        self._add(conv, Sender.AGENT, "استلمنا الدفع، شكراً لك! ✅" if lang == "ar"
                  else "Payment received, thank you! ✅", self._gap(t, 1), author=agent)
        if plan.status == TicketStatus.PAID:
            return
        t = self._gap(t, 60 * 26)
        self._status(ticket, conv, agent, TicketStatus.CONFIRMED, t)
        self._add(conv, Sender.AGENT,
                  f"حجزكم مؤكد 🎉 رقم الحجز {ticket.reference}. نرسل لكم التذاكر وقسائم الفندق قبل السفر بأسبوع. رحلة سعيدة!"
                  if lang == "ar" else
                  f"Your booking {ticket.reference} is confirmed 🎉 We'll send the tickets and hotel vouchers a week "
                  "before departure. Have a wonderful trip!", self._gap(t, 1), author=agent)
        t = self._gap(t, 30)
        self._close(conv, agent, t)

    def _cancel(self, ticket: Ticket, conv: Conversation, user: User, at: datetime) -> None:
        seats.release(self.db, ticket)
        if ticket.payment_reference:
            self._event(ticket, user, "payment_reference", at, ticket.payment_reference, None)
            ticket.payment_reference = None
        self._status(ticket, conv, user, TicketStatus.CANCELLED, at)
        self._close(conv, user, self._gap(at, 5))

    def _close(self, conv: Conversation, user: User, at: datetime) -> None:
        self._add(conv, Sender.SYSTEM, f"{user.full_name} closed the conversation", at)
        conv.status = ConversationStatus.CLOSED
        conv.assigned_to_id = None

    def _fill(self, text: str | None) -> str | None:
        """Sample answers that quote a package or the budget follow the profile's catalogue."""
        if not text or "{" not in text:
            return text
        pk = self.content.by_key
        return text.format(budget=self.content.budget, dubai_ar=pk["dubai"].ar,
                           dubai_child=f"{Decimal(pk['dubai'].child or 0):.0f}", georgia_en=pk["georgia"].en,
                           georgia_days=pk["georgia"].days, georgia_price=pk["georgia"].price)

    def _info(self, lang, channel, days_ago, closed, text, query, answer, follow, follow_answer) -> None:
        start = self.now - timedelta(days=days_ago)
        conv, customer = self._conversation(channel, start, lang)
        ctx = self._ctx(conv, customer)
        text, answer, follow_answer = self._fill(text), self._fill(answer), self._fill(follow_answer)
        if isinstance(query, dict):
            query = {k: int(self._fill(v)) if v == "{budget}" else v for k, v in query.items()}
        t = start
        self._add(conv, Sender.CUSTOMER, text, t)
        t = self._gap(t, 0.4)
        if query:
            args = query if isinstance(query, dict) else {"query": query}
            found = self._tool(ctx, conv, "search_packages", args, t)
            self._reply(conv, self._list_text(found, lang), t, [("search_packages", found)])
        else:
            self._reply(conv, answer, t, [])
        if follow:
            t = self._gap(t, 2)
            self._add(conv, Sender.CUSTOMER, follow, t)
            t = self._gap(t, 0.4)
            self._reply(conv, follow_answer, t, [])
        if closed:
            self._close(conv, self.users["support1"], self._gap(t, 60 * 20))

    def _handover(self, lang, channel, days_ago, staff_key, end_status, text, reason, staff_reply,
                  customer_reply) -> None:
        start = self.now - timedelta(days=days_ago)
        conv, customer = self._conversation(channel, start, lang)
        ctx = self._ctx(conv, customer)
        t = start
        self._add(conv, Sender.CUSTOMER, text, t)
        t = self._gap(t, 0.4)
        self._tool(ctx, conv, "request_human_agent", {"reason": reason}, t)
        self._reply(conv, "أكيد! حولتك لأحد مستشارينا وبيرد عليك هنا قريباً 🙏" if lang == "ar" else
                    "Of course! I've asked one of our consultants to join, they'll reply here shortly 🙏", t, [])
        if not staff_key:
            return  # waiting for the team
        staff = self.users[staff_key]
        t = self._gap(t, 25)
        self._add(conv, Sender.SYSTEM, f"{staff.full_name} took over the conversation", t)
        conv.assigned_to_id = staff.id
        t = self._gap(t, 2)
        self._add(conv, Sender.AGENT, staff_reply, t, author=staff)
        t = self._gap(t, 6)
        self._add(conv, Sender.CUSTOMER, customer_reply, t)
        if end_status == ConversationStatus.CLOSED:
            self._close(conv, staff, self._gap(t, 10))
        elif end_status == ConversationStatus.AI:
            t = self._gap(t, 3)
            self._add(conv, Sender.SYSTEM, f"{staff.full_name} handed the conversation back to the AI", t)
            conv.status = ConversationStatus.AI
            conv.handover_reason = None
            conv.assigned_to_id = None
