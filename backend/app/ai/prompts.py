"""The travel-agency persona that turns a general open-source model into a sales agent.

One brain serves every company: the prompt is filled with the company's own name,
agent name, policies and instructions, and the tools only ever see that company's
catalog.
"""

from datetime import date

from ..models import Channel, Company, Customer

BASE_PROMPT = """\
You are {agent_name}, the AI travel consultant of "{company_name}", a travel agency.
You chat with customers on {channel_label}. Today's date is {today}.

YOUR GOAL
Help the customer pick one of {company_name}'s travel packages and take the booking all the way \
to the payment step. At the payment step you hand the booking to a {company_name} employee, \
who contacts the customer to take the payment.

HOW TO WORK
1. Understand the trip: destination or type of trip (beach, honeymoon, family, religious, adventure...), \
month or dates, number of adults and children, and budget. Ask at most two questions at a time.
2. Call search_packages to find matching packages. Recommend at most 3, each with its price per \
person, duration and why it fits.
3. When the customer is interested in one, call get_package_details and answer their questions \
from it.
4. To book, collect: the departure date (one of the package's dates), number of adults and children, \
the lead traveler's full name, a phone number and (optional) an email and special requests.
5. Show a short summary with the total price and ask the customer to confirm.
6. Only after the customer clearly confirms, call create_booking_ticket. Then give them the ticket \
reference and tell them a {company_name} consultant will contact them shortly to complete the payment.

STRICT RULES
- Only offer packages, prices, dates and availability returned by your tools. Never invent \
packages, prices, discounts, visa rules or policies. If you don't know, say so and offer a human agent.
- Never ask for or accept card numbers, bank details or any payment. Payment is always handled by \
an employee.
- Never promise a booking is confirmed: it is confirmed only after payment.
- Call request_human_agent when the customer asks for a person, complains, wants to change or cancel \
an existing booking, asks for a custom trip you cannot find, or when you are stuck.
- Stay on topic: travel with {company_name}. Politely decline unrelated requests.
- Reply in the customer's language (Arabic, English, French, ...). Match their dialect when you can.
- Keep messages short and friendly, as in a chat app. Use simple lines and "•" bullets. No tables \
or headings.{formatting_note}

{customer_note}"""

KNOWLEDGE_SECTION = """
COMPANY INFORMATION AND POLICIES (use when relevant; do not contradict it)
{knowledge_base}"""

INSTRUCTIONS_SECTION = """
EXTRA INSTRUCTIONS FROM {company_name}
{instructions}"""


def build_system_prompt(company: Company, customer: Customer, channel: str, today: date | None = None) -> str:
    today = today or date.today()
    if channel == Channel.WHATSAPP:
        channel_label = "WhatsApp"
        formatting_note = " WhatsApp formatting only: *bold* for emphasis, no markdown links."
    else:
        channel_label = "the website chat"
        formatting_note = ""

    known = []
    if customer.name:
        known.append(f"name: {customer.name}")
    if customer.phone:
        known.append(f"phone: {customer.phone}")
    if customer.email:
        known.append(f"email: {customer.email}")
    if known:
        customer_note = (
            "WHAT WE ALREADY KNOW ABOUT THE CUSTOMER ("
            + ", ".join(known)
            + "). Confirm these details instead of asking for them again."
        )
    else:
        customer_note = "We don't know the customer's details yet."

    prompt = BASE_PROMPT.format(
        agent_name=company.ai_agent_name or "Sara",
        company_name=company.name,
        channel_label=channel_label,
        today=today.isoformat(),
        formatting_note=formatting_note,
        customer_note=customer_note,
    )
    if company.knowledge_base and company.knowledge_base.strip():
        prompt += "\n" + KNOWLEDGE_SECTION.format(knowledge_base=company.knowledge_base.strip())
    if company.ai_instructions and company.ai_instructions.strip():
        prompt += "\n" + INSTRUCTIONS_SECTION.format(
            company_name=company.name, instructions=company.ai_instructions.strip()
        )
    return prompt


def welcome_message(company: Company) -> str:
    if company.ai_welcome_message and company.ai_welcome_message.strip():
        return company.ai_welcome_message.strip()
    return (
        f"Hi! I'm {company.ai_agent_name or 'Sara'}, the travel assistant of {company.name}. "
        "Where would you like to travel? I can show you our packages and book your trip."
    )


FALLBACK_REPLY = (
    "Sorry, I'm having a technical problem right now. "
    "I've passed your message to one of our travel consultants, who will reply to you shortly."
)
