"""First-start data: the platform owner account and an optional demo travel company."""

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Company, Role, TravelPackage, User
from .permissions import ROLE_DEFAULT_PERMISSIONS
from .security import hash_password

log = logging.getLogger(__name__)

DEMO_KNOWLEDGE = """\
- Office hours: Sunday to Thursday, 9:00 to 18:00.
- Booking: a 30% deposit confirms the booking, the rest is due 21 days before departure.
- Payment methods: bank transfer, card payment link, or cash at our office. Our consultant sends the details.
- Cancellation: free up to 30 days before departure; 50% fee 29-8 days before; no refund within 7 days.
- Visas: we assist with tourist visas for Turkey, Egypt, Indonesia, Tanzania and Schengen (extra fee).
- Children: 2-11 years pay the child price; under 2 travel free (no seat, no bed).
- All prices are per person in a double room unless stated."""


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


DEMO_PACKAGES = [
    dict(title="Maldives Honeymoon Escape", destination="Malé", country="Maldives", duration_days=6,
         price_per_person=2450, child_price=None, tags=["honeymoon", "beach", "luxury", "island"],
         hotel_name="Coral Lagoon Water Villas", hotel_stars=5, seats_available=10, is_featured=True,
         departure_dates=_dates(21, 49, 77, 105),
         description="Five nights in an overwater villa with private sunset dinner, couples spa session and "
                     "snorkeling trip. Speedboat transfers from Malé airport.",
         includes=["Return flights", "Overwater villa, half board", "Speedboat transfers", "Couples spa 60 min",
                   "Private sunset dinner"],
         excludes=["Travel insurance", "Drinks outside meals"]),
    dict(title="Istanbul & Cappadocia Discovery", destination="Istanbul", country="Turkey", duration_days=8,
         price_per_person=1190, child_price=850, tags=["culture", "family", "history", "balloon"],
         hotel_name="Sultanahmet Palace / Cave Suites", hotel_stars=4, seats_available=24, is_featured=True,
         departure_dates=_dates(14, 35, 63, 91),
         description="Four nights in Istanbul (Hagia Sophia, Blue Mosque, Bosphorus cruise, Grand Bazaar) and "
                     "three nights in Cappadocia with a sunrise hot-air balloon ride.",
         includes=["Return flights + domestic flight", "Hotels with breakfast", "Guided tours", "Bosphorus cruise",
                   "Hot-air balloon ride"],
         excludes=["Turkey visa (we assist)", "Lunches and dinners"]),
    dict(title="Dubai Family Fun", destination="Dubai", country="United Arab Emirates", duration_days=5,
         price_per_person=980, child_price=540, tags=["family", "city", "shopping", "theme parks", "desert"],
         hotel_name="Marina Family Resort", hotel_stars=4, seats_available=30,
         departure_dates=_dates(10, 24, 38, 52, 66),
         description="Four nights in Dubai Marina with desert safari and BBQ dinner, Burj Khalifa observation deck, "
                     "and a full day at a theme park of your choice.",
         includes=["Return flights", "Hotel with breakfast", "Desert safari", "Burj Khalifa tickets",
                   "Theme park day pass", "Airport transfers"],
         excludes=["UAE visa fees where required"]),
    dict(title="Umrah Premium Package", destination="Makkah", country="Saudi Arabia", duration_days=10,
         price_per_person=1650, child_price=1200, tags=["umrah", "religious", "family"],
         hotel_name="Haram View Hotel (Makkah) / Taibah Suites (Madinah)", hotel_stars=5, seats_available=40,
         departure_dates=_dates(18, 46, 74),
         description="Six nights in Makkah within walking distance of the Haram and three nights in Madinah. "
                     "Guided Umrah with an experienced religious guide and Ziyarat tours.",
         includes=["Return flights", "Umrah visa", "5-star hotels with breakfast", "Private bus transfers",
                   "Religious guide", "Ziyarat tours"],
         excludes=["Lunches and dinners", "Personal expenses"]),
    dict(title="Bali Adventure & Beaches", destination="Bali", country="Indonesia", duration_days=9,
         price_per_person=1390, child_price=990, tags=["adventure", "beach", "nature", "honeymoon"],
         hotel_name="Ubud Jungle Lodge / Seminyak Beach Hotel", hotel_stars=4, seats_available=16,
         departure_dates=_dates(28, 56, 84),
         description="Rice terraces, waterfalls and temples in Ubud, white-water rafting and a sunrise trek on "
                     "Mount Batur, then relaxing beach days in Seminyak.",
         includes=["Return flights", "Hotels with breakfast", "Rafting", "Mount Batur sunrise trek",
                   "Temple tour", "Transfers"],
         excludes=["Visa on arrival fee", "Travel insurance"]),
    dict(title="Paris & Swiss Alps", destination="Paris", country="France", duration_days=10,
         price_per_person=2890, child_price=2100, tags=["europe", "honeymoon", "mountains", "culture"],
         hotel_name="Hotel Rive Gauche / Alpine Chalet Interlaken", hotel_stars=4, seats_available=12,
         departure_dates=_dates(40, 70, 100),
         description="Five nights in Paris (Eiffel Tower, Louvre, Seine cruise, Versailles) and four nights in "
                     "Interlaken with a Jungfraujoch excursion. Train Paris-Switzerland included.",
         includes=["Return flights", "Hotels with breakfast", "TGV train ticket", "Seine cruise",
                   "Jungfraujoch excursion"],
         excludes=["Schengen visa (we assist)", "City taxes"]),
    dict(title="Zanzibar Beach Retreat", destination="Zanzibar", country="Tanzania", duration_days=7,
         price_per_person=1290, child_price=790, tags=["beach", "relax", "island", "honeymoon"],
         hotel_name="Nungwi Palm Beach Resort", hotel_stars=4, seats_available=20,
         departure_dates=_dates(25, 53, 81),
         description="Six nights all-inclusive on Nungwi beach with a Stone Town tour, spice farm visit and a "
                     "dhow sunset cruise.",
         includes=["Return flights", "All-inclusive resort", "Stone Town tour", "Spice farm visit", "Sunset cruise"],
         excludes=["Tanzania visa fee", "Travel insurance"]),
    dict(title="Cairo & Nile Cruise", destination="Cairo", country="Egypt", duration_days=8,
         price_per_person=1050, child_price=700, tags=["history", "culture", "cruise", "family"],
         hotel_name="Giza Pyramids View Hotel / MS Nile Queen", hotel_stars=5, seats_available=26,
         departure_dates=_dates(12, 33, 61, 89),
         description="Pyramids of Giza, the Grand Egyptian Museum, then a four-night Nile cruise from Luxor to "
                     "Aswan with Karnak, Valley of the Kings and Abu Simbel.",
         includes=["Return flights", "Hotel + full-board cruise", "Egyptologist guide", "All entrance fees",
                   "Abu Simbel excursion"],
         excludes=["Egypt visa (we assist)", "Tips"]),
]


def seed_demo(db: Session) -> None:
    if db.scalar(select(Company).where(Company.slug == "sunrise-travel")):
        return
    company = Company(
        name="Sunrise Travel",
        slug="sunrise-travel",
        max_users=10,
        currency="USD",
        contact_email="hello@sunrise-travel.example",
        contact_phone="+1 555 0100",
        ai_agent_name="Sara",
        knowledge_base=DEMO_KNOWLEDGE,
        ai_instructions="Mention the 30% deposit when the customer asks how to pay.",
    )
    db.add(company)
    db.flush()
    for email, name, role, password in [
        ("admin@sunrise-travel.example", "Amira Admin", Role.COMPANY_ADMIN, "Admin123!"),
        ("support@sunrise-travel.example", "Sami Support", Role.SUPPORT, "Support123!"),
        ("tickets@sunrise-travel.example", "Tariq Tickets", Role.TICKET_AGENT, "Tickets123!"),
    ]:
        db.add(User(company_id=company.id, email=email, full_name=name, role=role,
                    password_hash=hash_password(password), permissions=list(ROLE_DEFAULT_PERMISSIONS[role])))
    for p in DEMO_PACKAGES:
        db.add(TravelPackage(company_id=company.id, currency="USD", **p))
    db.commit()
    log.info("Created demo company 'Sunrise Travel' (slug sunrise-travel)")
