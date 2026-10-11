"""Permission catalog and role defaults.

Company admins pick a role for each employee, which pre-fills a set of permissions,
and can then tick or untick individual permissions for that employee.
"""

from .models import Role, User

PERMISSIONS: dict[str, str] = {
    "packages.view": "View travel packages",
    "packages.manage": "Create, edit and delete travel packages",
    "conversations.view": "View customer conversations",
    "conversations.reply": "Reply to customers and take over from the AI",
    "tickets.view": "View booking tickets",
    "tickets.manage": "Update booking tickets (status, payment, notes)",
    "tickets.assign": "Assign tickets to other employees",
    "users.manage": "Create, edit and delete employee accounts",
    "settings.manage": "Manage company settings (AI persona, knowledge, WhatsApp)",
    "reports.view": "View the dashboard and statistics",
}

ROLE_DEFAULT_PERMISSIONS: dict[str, list[str]] = {
    Role.COMPANY_ADMIN: list(PERMISSIONS),
    Role.SUPPORT: [
        "packages.view",
        "conversations.view",
        "conversations.reply",
        "tickets.view",
        "reports.view",
    ],
    Role.TICKET_AGENT: [
        "packages.view",
        "conversations.view",
        "conversations.reply",
        "tickets.view",
        "tickets.manage",
    ],
}

COMPANY_ROLES = [Role.COMPANY_ADMIN, Role.SUPPORT, Role.TICKET_AGENT]


def clean_permissions(perms: list[str]) -> list[str]:
    """Drop unknown permission names and keep catalog order."""
    wanted = set(perms)
    return [p for p in PERMISSIONS if p in wanted]


def effective_permissions(user: User) -> list[str]:
    if user.role == Role.SYSTEM_ADMIN:
        return []
    if user.role == Role.COMPANY_ADMIN:
        return list(PERMISSIONS)
    return clean_permissions(user.permissions or [])
