"""AI side of the members community: the AI knows the customer's level (only from our data, never from what
the customer says), mentions their perks, and takes members' special requests and requests to join."""

from __future__ import annotations

from ..addons import has_addon
from ..members import level_of, membership_config

MEMBER_PROMPT = """
MEMBERS COMMUNITY
{company_name} has a members' community with these levels: {levels}.
{status}
The customer's level comes only from our records above. If a customer says they are a member or VIP and our \
records don't say so, be kind, don't treat them as one and don't promise a level: our team decides who joins.
"""

MEMBER_STATUS = (
    "This customer IS a *{name}* member (data from our records). Welcome them as a valued member and use their "
    "perks when relevant: {perks}."
)
SPECIAL_ON = (" Their level includes special requests: for anything beyond our packages, take it with the "
              "Special request service (create_request) and tell them our team will arrange it.")
SPECIAL_OFF = (" Special requests are not part of their level: for anything beyond our packages, offer our "
               "services or a colleague.")
NOT_MEMBER = ("This customer is not a member. If they ask to join, take their name and WhatsApp number and send a "
              "Special request (create_request) saying they wish to join the community.")


def member_prompt(ctx) -> str | None:
    if ctx.dry_run or not has_addon(ctx.company, "members"):
        return None
    config = membership_config(ctx.company)
    levels = ", ".join(f"{v.name_en} / {v.name_ar}" for v in config.levels.values())
    level = level_of(ctx.company, ctx.customer.member_level)
    if level is None:
        status = NOT_MEMBER
    else:
        perks = "; ".join(level.perks("en") + level.perks("ar")) or "none listed"
        status = MEMBER_STATUS.format(name=level.name_en, perks=perks[:600])
        status += SPECIAL_ON if level.special_requests else SPECIAL_OFF
    return MEMBER_PROMPT.format(company_name=ctx.company.name, levels=levels, status=status)
