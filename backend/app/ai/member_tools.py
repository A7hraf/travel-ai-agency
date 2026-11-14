"""AI side of the members community: the AI knows the customer's level (only from our data, never from what
the customer says), mentions their perks, and takes members' special requests and requests to join."""

from __future__ import annotations

from sqlalchemy import func, select

from ..addons import has_addon
from ..members import level_of, membership_config
from ..models import MemberRequest

MAX_OPEN_REQUESTS = 5  # per customer, so a chat can't flood the team

MEMBER_TOOL_DEFINITIONS: list[dict] = [{
    "type": "function",
    "function": {
        "name": "create_member_request",
        "description": (
            "Pass a request to the team: kind 'special' for a member's special request (anything beyond our "
            "packages: private transfer, restaurant or event booking, a surprise, an upgrade…), or kind 'join' when "
            "someone asks to become a member. Summarise and confirm with the customer first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["special", "join"]},
                "title": {"type": "string", "description": "Short title, e.g. 'Private yacht dinner on 12 Dec'"},
                "details": {"type": "string", "description": "Everything the team needs: dates, people, wishes, budget"},
            },
            "required": ["kind", "title"],
        },
    },
}]

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
SPECIAL_ON = (" For special requests beyond our packages, collect the details, confirm, then call "
              "create_member_request with kind 'special' and tell them our team will arrange it.")
SPECIAL_OFF = " Special requests are not part of their level: offer to hand over to our team instead."
NOT_MEMBER = ("This customer is not a member. If they ask to join, collect their name and phone number, confirm, "
              "and call create_member_request with kind 'join'.")


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


def create_member_request(ctx, kind="", title="", details="", **_) -> dict:
    if ctx.dry_run:
        return {"simulated": True, "note": "Test chat: no request was created."}
    if not has_addon(ctx.company, "members"):
        return {"error": "This company has no members community."}
    level = level_of(ctx.company, ctx.customer.member_level)
    if kind == "special":
        if level is None:
            return {"error": "This customer is not a member: special requests are for members. Offer a human instead."}
        if not level.special_requests:
            return {"error": "Special requests are not part of this member's level. Offer a human instead."}
    elif kind == "join":
        if level is not None:
            return {"error": "This customer is already a member."}
    else:
        return {"error": "kind must be 'special' or 'join'."}
    title = " ".join(str(title or "").split())[:200]
    if len(title) < 2:
        return {"error": "Give a short title."}
    open_count = ctx.db.scalar(select(func.count(MemberRequest.id)).where(
        MemberRequest.company_id == ctx.company.id, MemberRequest.customer_id == ctx.customer.id,
        MemberRequest.status.in_(("open", "in_progress")))) or 0
    if open_count >= MAX_OPEN_REQUESTS:
        return {"error": "This customer already has several open requests: the team will reply to them first."}
    ctx.db.add(MemberRequest(company_id=ctx.company.id, customer_id=ctx.customer.id,
                             conversation_id=ctx.conversation.id, kind=kind, level=ctx.customer.member_level,
                             title=title, details=str(details or "").strip()[:4000] or None))
    ctx.db.flush()
    return {"created": True, "next": "Our team will contact the customer about it."}


MEMBER_HANDLERS = {"create_member_request": create_member_request}
