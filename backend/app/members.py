"""Members community: three ranks and VIP. The company names the levels, writes their perks in both
languages and chooses what each level can do; staff with ``members.manage`` give each customer a level.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .branding import clean_text
from .models import Company

LEVELS: tuple[str, ...] = ("level1", "level2", "level3", "vip")
LevelKey = Literal["level1", "level2", "level3", "vip"]


class LevelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name_en: str = Field(min_length=1, max_length=40)
    name_ar: str = Field(min_length=1, max_length=40)
    perks_en: str = Field(default="", max_length=1000)  # one perk per line
    perks_ar: str = Field(default="", max_length=1000)
    special_requests: bool = False  # the AI takes special requests from this level
    priority: bool = False          # their chats are marked as priority in the inbox

    @field_validator("name_en", "name_ar")
    @classmethod
    def one_line(cls, v: str) -> str:
        v = clean_text(v, multiline=False)
        if not v:
            raise ValueError("A level needs a name")
        return v

    @field_validator("perks_en", "perks_ar")
    @classmethod
    def lines(cls, v: str) -> str:
        return clean_text(v, multiline=True)

    def perks(self, lang: str) -> list[str]:
        text = (self.perks_ar or self.perks_en) if lang == "ar" else (self.perks_en or self.perks_ar)
        return [line.strip(" -•\t") for line in text.split("\n") if line.strip(" -•\t")]


def _default_levels() -> dict[str, LevelConfig]:
    return {
        "level1": LevelConfig(name_en="Silver", name_ar="فضي",
                              perks_en="Priority replies\nMember-only offers",
                              perks_ar="أولوية في الرد\nعروض خاصة بالأعضاء"),
        "level2": LevelConfig(name_en="Gold", name_ar="ذهبي",
                              perks_en="Room upgrades when available\nFree date change once",
                              perks_ar="ترقية الغرف عند توفرها\nتغيير مجاني للموعد مرة واحدة"),
        "level3": LevelConfig(name_en="Platinum", name_ar="بلاتيني",
                              perks_en="A personal consultant\nSpecial requests at any time",
                              perks_ar="مستشار شخصي\nطلبات خاصة في أي وقت", special_requests=True),
        "vip": LevelConfig(name_en="VIP", name_ar="VIP",
                           perks_en="A dedicated team\nSpecial requests at any hour\nExperiences created for you",
                           perks_ar="فريق مخصص لك\nطلبات خاصة في أي ساعة\nتجارب تُصنع لك",
                           special_requests=True, priority=True),
    }


class MembershipConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    levels: dict[LevelKey, LevelConfig] = Field(default_factory=_default_levels)
    # The Community section of the customer page shows these levels.
    show_on_page: bool = True

    @field_validator("levels", mode="after")
    @classmethod
    def all_levels(cls, v: dict) -> dict:
        defaults = _default_levels()
        return {k: v.get(k, defaults[k]) for k in LEVELS}


def membership_config(company: Company) -> MembershipConfig:
    raw: Any = company.membership if isinstance(company.membership, dict) else {}
    try:
        return MembershipConfig.model_validate(raw)
    except ValueError:
        return MembershipConfig()


def level_of(company: Company, key: str | None) -> LevelConfig | None:
    if key not in LEVELS:
        return None
    return membership_config(company).levels[key]


def staff_member_levels(company: Company) -> dict[str, dict] | None:
    """For the staff app (badges in the inbox and customers list), when the feature is on."""
    from .addons import has_addon  # noqa: PLC0415

    if not has_addon(company, "members"):
        return None
    levels = membership_config(company).levels
    return {k: {"name_en": v.name_en, "name_ar": v.name_ar, "priority": v.priority} for k, v in levels.items()}


def public_member_levels(company: Company) -> list[dict] | None:
    """For the Community section of the customer page: names and perks of each level."""
    from .addons import has_addon  # noqa: PLC0415

    config = membership_config(company)
    if not has_addon(company, "members") or not config.show_on_page:
        return None
    return [{"key": k, "name_en": v.name_en, "name_ar": v.name_ar, "perks_en": v.perks("en"),
             "perks_ar": v.perks("ar")} for k, v in config.levels.items()]
