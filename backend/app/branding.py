"""Company branding: customer page look and content, and the employee dashboard colours.

Stored as JSON on the company. The customer-page part (colours, texts, sections, photos, package
cards) is edited by the company admin and the platform owner; the dashboard colours and the
"Powered by Ghanjah" line are set by the platform owner only.

Old saved JSON keeps working: every new field has a default, and designs saved before the page
editor (no "version") get "How booking works" back in their section list and their old list
layout turned into the "compact" card style.
"""

import re
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .models import Company

HEX = r"^#[0-9a-fA-F]{6}$"
VERSION = 2
SECTIONS = ("search", "featured", "offers", "how", "about", "contact")
DASHBOARD_FIELDS = {"dashboard_color", "dashboard_sidebar"}
IMAGE_FIELDS = ("logo", "hero_image", "about_image", "about_bg_image", "how_bg_image")
LANGS = ("en", "ar")

Section = Literal["search", "featured", "offers", "how", "about", "contact"]

# Customer-page texts that can be replaced, with their maximum length. The keys are the string
# entries of STOREFRONT_TEXT in frontend/src/i18n.ts; texts built from a template may use {agent}
# (the AI consultant's name) and {company}; list entries are numbered (trust1, cat0, how1Title…).
# Counted texts ("3 days", "2 adults") stay with the code. tests/test_page_editor.py keeps this
# list in step with the frontend.
SHORT, MEDIUM, LONG = 80, 200, 600
TEXT_KEYS: dict[str, int] = {
    # Hero and search
    "online": SHORT, "fromOman": SHORT, "heroA": SHORT, "heroB": SHORT,
    "searchPlaceholder": SHORT, "webSearchPlaceholder": SHORT, "budgetPlaceholder": SHORT,
    "webBudgetPlaceholder": SHORT, "findTrips": SHORT, "trust1": SHORT, "trust2": SHORT, "trust3": SHORT,
    # Navigation
    "navTrips": SHORT, "navHow": SHORT, "navAbout": SHORT, "switchTo": SHORT, "whatsapp": SHORT,
    # Trips
    "featuredTitle": SHORT, "offers": SHORT, "tripsOnSale": SHORT,
    "cat0": SHORT, "cat1": SHORT, "cat2": SHORT, "cat3": SHORT, "cat4": SHORT, "cat5": SHORT,
    "pricesNote": MEDIUM, "perPerson": SHORT, "perAdult": SHORT, "perChild": SHORT, "from": SHORT,
    "noMatch": MEDIUM, "askCustom": SHORT, "clear": SHORT, "comingSoon": MEDIUM, "askNow": SHORT,
    # Buttons
    "book": SHORT, "bookWith": SHORT, "bookThis": SHORT, "viewTrip": SHORT,
    # Package details
    "included": SHORT, "notIncluded": SHORT, "departures": SHORT, "flexible": SHORT, "soldOut": SHORT,
    # How booking works
    "howKicker": SHORT, "howTitle": MEDIUM, "howAccent": SHORT, "howEnd": MEDIUM,
    "how1Title": SHORT, "how1Text": LONG, "how2Title": SHORT, "how2Text": LONG, "how3Title": SHORT, "how3Text": LONG,
    # About and contact
    "aboutQuote": MEDIUM, "contactTitle": SHORT, "contactText": LONG,
    # Footer
    "footer": MEDIUM,
    # Chat
    "chatWith": SHORT, "chatButtonSub": SHORT, "aiSub": SHORT, "humanSub": SHORT, "consultant": SHORT,
    "live": SHORT, "welcome": LONG, "qHoney": SHORT, "qFamily": SHORT, "qHuman": SHORT, "typeHere": SHORT,
    "askAnything": SHORT, "newChat": SHORT, "newChatQ": MEDIUM, "cancel": SHORT, "start": SHORT,
    "retry": SHORT, "tooFast": MEDIUM, "notSent": MEDIUM,
    # Booking cards in the chat
    "summary": SHORT, "sPkg": SHORT, "sDate": SHORT, "sPax": SHORT, "sTotal": SHORT,
    "confirmBooking": SHORT, "change": SHORT, "yesConfirm": MEDIUM, "changeMsg": MEDIUM,
    "booked": SHORT, "bookedRef": SHORT,
}
# Texts that may keep line breaks; every other text is one line.
MULTILINE_KEYS = {"welcome", "how1Text", "how2Text", "how3Text", "contactText"}

# Control characters (keeping tab and line feed) and the bidirectional overrides that can make a
# text read differently from what was typed.
_CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f‪-‮⁦-⁩]")


def clean_text(value: str, multiline: bool) -> str:
    value = value.replace("\r\n", "\n").replace("\t", " ")
    value = _CONTROL.sub("", value)
    if not multiline:
        value = " ".join(value.split("\n"))
    return value.strip()


def _image_ref(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("/api/media/") or value.startswith("https://"):
        return value
    raise ValueError("must be an uploaded image or an https:// address")


class PageElements(BaseModel):
    """Smaller parts of the page that can be hidden. "powered_by" is for the platform owner only."""

    model_config = ConfigDict(extra="forbid")

    kicker: bool = True          # small line above the title ("Sara is online" / "From Oman to the world")
    trust: bool = True           # three trust points under the search (computer)
    lang_switch: bool = True     # English / العربية button
    nav_links: bool = True       # Trips · How it works · About (computer)
    nav_phone: bool = True       # phone number in the top bar (computer)
    whatsapp_icon: bool = True   # WhatsApp icon in the top bar (phone)
    budget_filter: bool = True   # maximum budget field
    chips: bool = True           # trip-type chips (All / Honeymoon / …)
    hero_chat: bool = True       # live chat card next to the title (computer)
    chat_launcher: bool = True   # "Chat with Sara" bar (phone) and floating button (computer)
    offers_count: bool = True    # "3 / 8" next to "Our offers" (phone)
    prices_note: bool = True     # "Prices in Omani rials…"
    footer_note: bool = True     # footer sentence
    powered_by: bool = True      # "Powered by Ghanjah" (platform owner only)


class CardDesign(BaseModel):
    """How packages are shown on the phone and computer page."""

    model_config = ConfigDict(extra="forbid")

    style: Literal["poster", "photo", "compact"] = "poster"
    columns: Literal[2, 3, 4] = 3
    show_price: bool = True
    show_duration: bool = True
    show_hotel: bool = False
    show_next_date: bool = False
    show_seats: bool = False
    show_tags: bool = False
    per_person: bool = False      # "per person" after the price
    show_button: bool = True      # Book button on the card


Texts = dict[str, dict[str, str]]


def _check_texts(value: Any) -> Texts:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("texts must be an object with 'en' and 'ar'")
    out: Texts = {lang: {} for lang in LANGS}
    for lang, entries in value.items():
        if lang not in LANGS:
            raise ValueError(f"unknown language '{lang}' in texts")
        if entries is None:
            continue
        if not isinstance(entries, dict):
            raise ValueError("texts of a language must be an object")
        for key, text in entries.items():
            if key not in TEXT_KEYS:
                raise ValueError(f"'{key}' is not an editable text")
            if text is None:
                continue
            if not isinstance(text, str):
                raise ValueError(f"text '{key}' must be a string")
            text = clean_text(text, key in MULTILINE_KEYS)
            if len(text) > TEXT_KEYS[key]:
                raise ValueError(f"text '{key}' is too long (maximum {TEXT_KEYS[key]} characters)")
            if text:  # empty = use the standard text
                out[lang][key] = text
    return out


def _migrate(data: Any) -> Any:
    """Designs saved before the page editor: "How booking works" was always shown after the trips,
    and the "list" layout showed compact rows with the hotel and the price per adult."""
    if not isinstance(data, dict) or "version" in data:
        return data
    data = dict(data)
    sections = data.get("sections")
    if isinstance(sections, list) and "how" not in sections:
        trips = [i for i, s in enumerate(sections) if s in ("featured", "offers")]
        at = trips[-1] + 1 if trips else len([s for s in sections if s == "search"])
        data["sections"] = [*sections[:at], "how", *sections[at:]]
    if data.get("layout") == "list" and "cards" not in data:
        data["cards"] = {"style": "compact", "show_hotel": True, "per_person": True}
    data["version"] = VERSION
    return data


class Branding(BaseModel):
    # Defaults follow the Ghanjah brand: Gulf Cyan for actions, Ink for the sidebar.
    version: int = VERSION
    # Colours of the customer page (empty = the standard dark design)
    primary_color: str = Field(default="#0088b0", pattern=HEX)   # buttons, links, highlighted word
    accent_color: str = Field(default="#4fb6dc", pattern=HEX)    # AI consultant avatar
    bg_color: str | None = Field(default=None, pattern=HEX)      # page background
    surface_color: str | None = Field(default=None, pattern=HEX)  # cards and fields
    text_color: str | None = Field(default=None, pattern=HEX)    # text
    highlight_color: str | None = Field(default=None, pattern=HEX)  # "Live", few seats left, the team
    logo: str | None = Field(default=None, max_length=500)
    # Top banner
    hero_style: Literal["gradient", "image", "solid"] = "gradient"
    hero_image: str | None = Field(default=None, max_length=500)
    hero_title_en: str = Field(default="", max_length=120)
    hero_title_ar: str = Field(default="", max_length=120)
    hero_text_en: str = Field(default="", max_length=400)
    hero_text_ar: str = Field(default="", max_length=400)
    # About us
    about_title_en: str = Field(default="", max_length=120)
    about_title_ar: str = Field(default="", max_length=120)
    about_en: str = Field(default="", max_length=3000)
    about_ar: str = Field(default="", max_length=3000)
    about_image: str | None = Field(default=None, max_length=500)
    about_bg_image: str | None = Field(default=None, max_length=500)
    how_bg_image: str | None = Field(default=None, max_length=500)
    # Structure
    sections: list[Section] = Field(default_factory=lambda: list(SECTIONS))
    elements: PageElements = Field(default_factory=PageElements)
    # Package cards
    card_style: Literal["rounded", "square"] = "rounded"
    layout: Literal["grid", "list"] = "grid"  # kept for older clients; follows cards.style
    cards: CardDesign = Field(default_factory=CardDesign)
    # Texts replacing the standard ones, per language
    texts: Texts = Field(default_factory=lambda: {lang: {} for lang in LANGS})
    # Employee dashboard (platform owner only)
    dashboard_color: str = Field(default="#0088b0", pattern=HEX)
    dashboard_sidebar: str = Field(default="#0f0e0d", pattern=HEX)

    @model_validator(mode="before")
    @classmethod
    def migrate(cls, data: Any) -> Any:
        return _migrate(data)

    @field_validator(*IMAGE_FIELDS)
    @classmethod
    def check_image(cls, v: str | None) -> str | None:
        return _image_ref(v)

    @field_validator("hero_title_en", "hero_title_ar", "about_title_en", "about_title_ar")
    @classmethod
    def one_line(cls, v: str) -> str:
        return clean_text(v, multiline=False)

    @field_validator("hero_text_en", "hero_text_ar", "about_en", "about_ar")
    @classmethod
    def paragraph(cls, v: str) -> str:
        return clean_text(v, multiline=True)

    @field_validator("bg_color", "surface_color", "text_color", "highlight_color", mode="before")
    @classmethod
    def empty_colour(cls, v: Any) -> Any:
        return v or None

    @field_validator("texts", mode="before")
    @classmethod
    def check_texts(cls, v: Any) -> Texts:
        return _check_texts(v)

    @field_validator("sections")
    @classmethod
    def unique_sections(cls, v: list[str]) -> list[str]:
        seen: list[str] = []
        for s in v:
            if s not in seen:
                seen.append(s)
        return seen

    @model_validator(mode="after")
    def follow_card_style(self) -> "Branding":
        self.layout = "list" if self.cards.style == "compact" else "grid"
        return self


class BrandingUpdate(BaseModel):
    """Partial update: only the fields sent are changed. `elements` and `cards` are merged key by
    key; `texts` replaces the texts of each language sent."""

    primary_color: str | None = Field(default=None, pattern=HEX)
    accent_color: str | None = Field(default=None, pattern=HEX)
    bg_color: str | None = None
    surface_color: str | None = None
    text_color: str | None = None
    highlight_color: str | None = None
    logo: str | None = None
    hero_style: Literal["gradient", "image", "solid"] | None = None
    hero_image: str | None = None
    hero_title_en: str | None = Field(default=None, max_length=120)
    hero_title_ar: str | None = Field(default=None, max_length=120)
    hero_text_en: str | None = Field(default=None, max_length=400)
    hero_text_ar: str | None = Field(default=None, max_length=400)
    about_title_en: str | None = Field(default=None, max_length=120)
    about_title_ar: str | None = Field(default=None, max_length=120)
    about_en: str | None = Field(default=None, max_length=3000)
    about_ar: str | None = Field(default=None, max_length=3000)
    about_image: str | None = None
    about_bg_image: str | None = None
    how_bg_image: str | None = None
    sections: list[Section] | None = None
    elements: dict[str, bool] | None = None
    card_style: Literal["rounded", "square"] | None = None
    layout: Literal["grid", "list"] | None = None
    cards: dict[str, Any] | None = None
    texts: dict[str, dict[str, Any] | None] | None = None
    dashboard_color: str | None = Field(default=None, pattern=HEX)
    dashboard_sidebar: str | None = Field(default=None, pattern=HEX)

    @field_validator(*IMAGE_FIELDS)
    @classmethod
    def check_image(cls, v: str | None) -> str | None:
        return _image_ref(v)

    def image_urls(self) -> list[str]:
        """Every photo address sent, to check that it belongs to the company."""
        return [url for url in (getattr(self, f) for f in IMAGE_FIELDS) if url]


class PublicBranding(BaseModel):
    """What the customer page needs (no dashboard colours)."""

    primary_color: str
    accent_color: str
    bg_color: str | None
    surface_color: str | None
    text_color: str | None
    highlight_color: str | None
    logo: str | None
    hero_style: str
    hero_image: str | None
    hero_title_en: str
    hero_title_ar: str
    hero_text_en: str
    hero_text_ar: str
    about_title_en: str
    about_title_ar: str
    about_en: str
    about_ar: str
    about_image: str | None
    about_bg_image: str | None
    how_bg_image: str | None
    sections: list[str]
    elements: PageElements
    card_style: str
    layout: str
    cards: CardDesign
    texts: Texts


class DashboardBranding(BaseModel):
    logo: str | None
    dashboard_color: str
    dashboard_sidebar: str


def get_branding(company: Company) -> Branding:
    try:
        return Branding.model_validate(company.branding or {})
    except ValueError:
        # One bad value must not reset the whole design: keep every field that is still valid.
        raw = company.branding if isinstance(company.branding, dict) else {}
        raw = _migrate(raw)
        kept: dict[str, Any] = {}
        for key, value in raw.items():
            if key not in Branding.model_fields:
                continue
            try:
                Branding.model_validate(kept | {key: value})
                kept[key] = value
            except ValueError:
                pass
        return Branding.model_validate(kept)


def apply_update(company: Company, update: BrandingUpdate, allow_dashboard: bool) -> Branding:
    """`allow_dashboard` is True for the platform owner: dashboard colours and "Powered by"."""
    data = update.model_dump(exclude_unset=True)
    current = get_branding(company)
    if not allow_dashboard:
        for key in DASHBOARD_FIELDS:
            data.pop(key, None)
    merged = current.model_dump() | data
    if "elements" in data:
        merged["elements"] = current.elements.model_dump() | (data["elements"] or {})
        if not allow_dashboard:
            merged["elements"]["powered_by"] = current.elements.powered_by
    if "cards" in data:
        merged["cards"] = current.cards.model_dump() | (data["cards"] or {})
    if "texts" in data:
        merged["texts"] = current.texts | {lang: entries or {} for lang, entries in (data["texts"] or {}).items()}
    if "layout" in data and "cards" not in data:  # older clients switch the layout only
        merged["cards"]["style"] = "compact" if data["layout"] == "list" else (
            "poster" if current.cards.style == "compact" else current.cards.style)
    try:
        branding = Branding.model_validate(merged)  # re-validates every field
    except ValidationError as exc:
        err = exc.errors()[0]
        msg = str(err.get("msg", "Invalid branding")).removeprefix("Value error, ")
        raise HTTPException(422, msg) from exc
    company.branding = branding.model_dump()
    return branding


def public_branding(company: Company) -> PublicBranding:
    return PublicBranding(**get_branding(company).model_dump(exclude=DASHBOARD_FIELDS | {"version"}))


def branding_image_urls(branding: dict | None) -> set[str]:
    """Photos a saved design uses (so unused-photo clean-up keeps them)."""
    branding = branding or {}
    return {branding[f] for f in IMAGE_FIELDS if isinstance(branding.get(f), str)}


def welcome_override(company: Company, lang: str) -> str | None:
    """The chat welcome written on the page editor, with the names filled in."""
    text = get_branding(company).texts.get("ar" if lang == "ar" else "en", {}).get("welcome")
    if not text:
        return None
    return text.replace("{agent}", company.ai_agent_name or "Sara").replace("{company}", company.name)


def dashboard_branding(company: Company) -> DashboardBranding:
    b = get_branding(company)
    return DashboardBranding(logo=b.logo, dashboard_color=b.dashboard_color, dashboard_sidebar=b.dashboard_sidebar)
