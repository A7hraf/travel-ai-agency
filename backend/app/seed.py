"""First-start data: the platform owner account and an optional demo travel company (Muscat, OMR)."""

import logging
import secrets
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Company, Role, TrainingExample, TravelPackage, User
from .permissions import ROLE_DEFAULT_PERMISSIONS
from .security import hash_password, revoke_sessions_now, verify_password

log = logging.getLogger(__name__)

DEFAULT_ADMIN_PASSWORD = "ChangeMe123!"
DEMO_SLUG = "sunrise-travel"

# Logins of the demo company. Outside production these fixed passwords make trying the
# app easy; in production the demo staff get random passwords instead.
DEMO_STAFF = [
    ("Company admin", "admin@sunrise-travel.example", "Amira Admin", Role.COMPANY_ADMIN, "Admin123!"),
    ("Support", "support@sunrise-travel.example", "Sami Support", Role.SUPPORT, "Support123!"),
    ("Ticket employee", "tickets@sunrise-travel.example", "Tariq Tickets", Role.TICKET_AGENT, "Tickets123!"),
]

DEMO_KNOWLEDGE = """\
- Office: Al Khuwair, Muscat. Open Sunday to Thursday, 8:00 to 17:00.
- All trips depart from Muscat International Airport (MCT) unless stated.
- Prices are in Omani rials (OMR), per person in a double room.
- Booking: a 30% deposit confirms the booking; the rest is due 21 days before departure.
- Payment: bank transfer, card payment link, or cash at our office. The consultant sends the details.
- Cancellation: free up to 30 days before departure; 50% fee 29-8 days before; no refund within 7 days.
- Visas: we help with tourist visas for Turkey, Egypt, Indonesia, Tanzania, Georgia and Schengen (extra fee).
- Children: 2-11 years pay the child price; under 2 travel free (no seat, no bed)."""

DEMO_TRAINING = [
    ("Can I pay in installments?",
     "Yes. For bookings above 300 OMR you can pay 30% now and the rest in two monthly payments. "
     "Our consultant arranges it when they call you."),
    ("هل الأسعار تشمل تذاكر الطيران؟",
     "نعم، كل باقاتنا تشمل تذاكر الطيران ذهاباً وإياباً من مطار مسقط الدولي، إلا إذا ذُكر غير ذلك في الباقة."),
    ("Where is your office?",
     "Our office is in Al Khuwair, Muscat, open Sunday to Thursday from 8:00 to 17:00."),
]


def ensure_system_admin(db: Session) -> None:
    s = get_settings()
    if db.scalar(select(User).where(User.role == Role.SYSTEM_ADMIN)):
        return
    db.add(
        User(
            company_id=None,
            email=s.system_admin_email.lower(),
            full_name=s.system_admin_name,
            password_hash=hash_password(s.system_admin_password),
            role=Role.SYSTEM_ADMIN,
            permissions=[],
        )
    )
    db.commit()
    log.info("Created system admin account %s", s.system_admin_email)


def _dates(*offsets: int) -> list[str]:
    today = date.today()
    return [(today + timedelta(days=o)).isoformat() for o in offsets]


def _omr(value: str) -> Decimal:
    return Decimal(value)


DEMO_PACKAGES = [
    dict(title="Maldives Honeymoon Escape", destination="Malé", country="Maldives", duration_days=6,
         price_per_person=_omr("945.000"), child_price=None, is_featured=True,
         tags=["honeymoon", "beach", "luxury", "island", "شهر عسل", "شاطئ", "المالديف", "جزر"],
         hotel_name="Coral Lagoon Water Villas", hotel_stars=5, seats_available=10,
         departure_dates=_dates(21, 49, 77, 105),
         description="Five nights in an overwater villa with a private sunset dinner, a couples spa session and a "
                     "snorkeling trip. Speedboat transfers from Malé airport.",
         includes=["Return flights from Muscat", "Overwater villa, half board", "Speedboat transfers",
                   "Couples spa 60 min", "Private sunset dinner"],
         excludes=["Travel insurance", "Drinks outside meals"]),
    dict(title="Salalah Khareef Weekend", destination="Salalah", country="Oman", duration_days=3,
         price_per_person=_omr("125.500"), child_price=_omr("85.000"), is_featured=True,
         tags=["khareef", "family", "nature", "domestic", "صلالة", "خريف", "ظفار", "عمان", "عائلي"],
         hotel_name="Salalah Garden Resort", hotel_stars=4, seats_available=40,
         departure_dates=_dates(9, 16, 23, 30),
         description="Two nights in Salalah during the green khareef season: Ain Razat, Wadi Darbat, Mughsail "
                     "beach and the frankincense souq, with a local driver-guide.",
         includes=["Return flights Muscat-Salalah", "Hotel with breakfast", "Full-day guided tour",
                   "Airport transfers"],
         excludes=["Lunches and dinners"]),
    dict(title="Istanbul & Cappadocia Discovery", destination="Istanbul", country="Turkey", duration_days=8,
         price_per_person=_omr("455.000"), child_price=_omr("325.000"), is_featured=True,
         tags=["culture", "family", "history", "balloon", "تركيا", "اسطنبول", "كبادوكيا", "عائلي"],
         hotel_name="Sultanahmet Palace / Cave Suites", hotel_stars=4, seats_available=24,
         departure_dates=_dates(14, 35, 63, 91),
         description="Four nights in Istanbul (Hagia Sophia, Blue Mosque, Bosphorus cruise, Grand Bazaar) and three "
                     "nights in Cappadocia with a sunrise hot-air balloon ride.",
         includes=["Return flights + domestic flight", "Hotels with breakfast", "Guided tours", "Bosphorus cruise",
                   "Hot-air balloon ride"],
         excludes=["Lunches and dinners"]),
    dict(title="Georgia: Tbilisi & Batumi", destination="Tbilisi", country="Georgia", duration_days=7,
         price_per_person=_omr("365.000"), child_price=_omr("260.000"),
         tags=["nature", "mountains", "family", "جورجيا", "تبليسي", "باتومي", "طبيعة", "جبال"],
         hotel_name="Old Town Tbilisi Hotel / Batumi Sea View", hotel_stars=4, seats_available=20,
         departure_dates=_dates(18, 46, 74),
         description="Three nights in Tbilisi with a day trip to Kazbegi mountains, then three nights by the sea in "
                     "Batumi. Private car with an Arabic-speaking driver.",
         includes=["Return flights", "Hotels with breakfast", "Private car and driver", "Kazbegi day trip"],
         excludes=["Lunches and dinners", "Personal expenses"]),
    dict(title="Zanzibar Beach Retreat", destination="Zanzibar", country="Tanzania", duration_days=7,
         price_per_person=_omr("495.000"), child_price=_omr("305.000"),
         tags=["beach", "relax", "island", "honeymoon", "زنجبار", "تنزانيا", "شاطئ", "جزيرة"],
         hotel_name="Nungwi Palm Beach Resort", hotel_stars=4, seats_available=20,
         departure_dates=_dates(25, 53, 81),
         description="Six nights all-inclusive on Nungwi beach with a Stone Town tour, a spice farm visit and a dhow "
                     "sunset cruise.",
         includes=["Return flights", "All-inclusive resort", "Stone Town tour", "Spice farm visit", "Sunset cruise"],
         excludes=["Visa fee", "Travel insurance"]),
    dict(title="Umrah Premium Package", destination="Makkah", country="Saudi Arabia", duration_days=10,
         price_per_person=_omr("520.000"), child_price=_omr("390.000"),
         tags=["umrah", "religious", "family", "عمرة", "مكة", "المدينة", "السعودية"],
         hotel_name="Haram View Hotel (Makkah) / Taibah Suites (Madinah)", hotel_stars=5, seats_available=40,
         departure_dates=_dates(12, 40, 68),
         description="Six nights in Makkah within walking distance of the Haram and three nights in Madinah, with an "
                     "experienced religious guide and Ziyarat tours.",
         includes=["Return flights", "Umrah visa", "5-star hotels with breakfast", "Private bus transfers",
                   "Religious guide", "Ziyarat tours"],
         excludes=["Lunches and dinners", "Personal expenses"]),
    dict(title="Dubai Family Fun", destination="Dubai", country="United Arab Emirates", duration_days=5,
         price_per_person=_omr("285.000"), child_price=_omr("165.000"),
         tags=["family", "city", "shopping", "theme parks", "دبي", "الامارات", "تسوق", "عائلي"],
         hotel_name="Marina Family Resort", hotel_stars=4, seats_available=30,
         departure_dates=_dates(10, 24, 38, 52),
         description="Four nights in Dubai Marina with a desert safari and BBQ dinner, the Burj Khalifa observation "
                     "deck and a full day at a theme park of your choice.",
         includes=["Return flights", "Hotel with breakfast", "Desert safari", "Burj Khalifa tickets",
                   "Theme park day pass", "Airport transfers"],
         excludes=["Lunches and dinners"]),
    dict(title="Bali Adventure & Beaches", destination="Bali", country="Indonesia", duration_days=9,
         price_per_person=_omr("535.000"), child_price=_omr("380.000"),
         tags=["adventure", "beach", "nature", "honeymoon", "بالي", "اندونيسيا", "مغامرة", "شاطئ"],
         hotel_name="Ubud Jungle Lodge / Seminyak Beach Hotel", hotel_stars=4, seats_available=16,
         departure_dates=_dates(28, 56, 84),
         description="Rice terraces, waterfalls and temples in Ubud, rafting and a sunrise trek on Mount Batur, then "
                     "beach days in Seminyak.",
         includes=["Return flights", "Hotels with breakfast", "Rafting", "Mount Batur sunrise trek", "Transfers"],
         excludes=["Visa on arrival fee", "Travel insurance"]),
    dict(title="Cairo & Nile Cruise", destination="Cairo", country="Egypt", duration_days=8,
         price_per_person=_omr("405.000"), child_price=_omr("270.000"),
         tags=["history", "culture", "cruise", "family", "مصر", "القاهرة", "النيل", "الاقصر"],
         hotel_name="Giza Pyramids View Hotel / MS Nile Queen", hotel_stars=5, seats_available=26,
         departure_dates=_dates(15, 43, 71),
         description="The Pyramids of Giza and the Grand Egyptian Museum, then a four-night Nile cruise from Luxor to "
                     "Aswan with Karnak, the Valley of the Kings and Abu Simbel.",
         includes=["Return flights", "Hotel + full-board cruise", "Egyptologist guide", "All entrance fees"],
         excludes=["Visa", "Tips"]),
    dict(title="Paris & Swiss Alps", destination="Paris", country="France", duration_days=10,
         price_per_person=_omr("1110.000"), child_price=_omr("805.000"),
         tags=["europe", "honeymoon", "mountains", "culture", "فرنسا", "باريس", "سويسرا", "اوروبا"],
         hotel_name="Hotel Rive Gauche / Alpine Chalet Interlaken", hotel_stars=4, seats_available=12,
         departure_dates=_dates(40, 70, 100),
         description="Five nights in Paris (Eiffel Tower, Louvre, Seine cruise) and four nights in Interlaken with a "
                     "Jungfraujoch excursion. Train Paris-Switzerland included.",
         includes=["Return flights", "Hotels with breakfast", "TGV train ticket", "Seine cruise",
                   "Jungfraujoch excursion"],
         excludes=["Schengen visa (we assist)", "City taxes"]),
]


def seed_demo(db: Session, production: bool = False) -> None:
    if db.scalar(select(Company).where(Company.slug == DEMO_SLUG)):
        return
    company = Company(
        name="Sunrise Travel",
        slug=DEMO_SLUG,
        max_users=10,
        currency="OMR",
        contact_email="hello@sunrise-travel.example",
        contact_phone="+968 9000 0000",
        ai_agent_name="Sara",
        knowledge_base=DEMO_KNOWLEDGE,
        ai_instructions="Mention the 30% deposit when the customer asks how to pay.",
    )
    db.add(company)
    db.flush()
    for _, email, name, role, password in DEMO_STAFF:
        db.add(User(company_id=company.id, email=email, full_name=name, role=role,
                    password_hash=hash_password(secrets.token_urlsafe(16) if production else password),
                    permissions=list(ROLE_DEFAULT_PERMISSIONS[role])))
    for package in DEMO_PACKAGES:
        db.add(TravelPackage(company_id=company.id, currency="OMR", **package))
    for question, answer in DEMO_TRAINING:
        db.add(TrainingExample(company_id=company.id, question=question, answer=answer))
    db.commit()
    log.info("Created demo company 'Sunrise Travel' (slug %s)", DEMO_SLUG)


def protect_demo_accounts(db: Session) -> None:
    """Production: demo logins whose password is the public one get a random password."""
    for _, email, _, _, password in DEMO_STAFF:
        user = db.scalar(select(User).where(User.email == email))
        if user is not None and verify_password(password, user.password_hash):
            user.password_hash = hash_password(secrets.token_urlsafe(16))
            user.tokens_valid_after = revoke_sessions_now()
            log.warning("Demo login %s had its public password; it was replaced with a random one", email)
    db.commit()


def demo_accounts() -> list[dict]:
    """Logins shown on the login page outside production."""
    s = get_settings()
    accounts = []
    if s.system_admin_password == DEFAULT_ADMIN_PASSWORD:
        accounts.append({"label": "Platform owner", "email": s.system_admin_email, "password": DEFAULT_ADMIN_PASSWORD})
    accounts += [{"label": label, "email": email, "password": pw} for label, email, _, _, pw in DEMO_STAFF]
    return accounts
