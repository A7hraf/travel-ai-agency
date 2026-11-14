"""Shapes of the business trip requests. There are three views of one request, each with only what that
party may see: the travel company (everything), the client (no vendor, no cost) and the vendor (no client
identity, no client price, traveller names only after approval)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Category = Literal["flight", "hotel", "transport", "activity", "food"]
CATEGORIES: tuple[str, ...] = ("flight", "hotel", "transport", "activity", "food")
MAX_CHOICES = 3  # choices per part sent to the client
MAX_OPTIONS = 30  # options of one request


def _line(v: str | None) -> str | None:
    if v is None:
        return None
    v = " ".join(v.split())
    return v or None


def _text(v: str | None) -> str | None:
    if v is None:
        return None
    v = "\n".join(line.rstrip() for line in v.replace("\r\n", "\n").split("\n")).strip()
    return v or None


class TripRequestIn(BaseModel):
    purpose: str | None = Field(default=None, max_length=200)
    origin: str | None = Field(default=None, max_length=120)
    destination: str = Field(min_length=2, max_length=120)
    depart_date: date | None = None
    return_date: date | None = None
    travellers: int = Field(default=1, ge=1, le=500)
    traveller_names: str | None = Field(default=None, max_length=4000)
    needs: list[Category] = Field(min_length=1, max_length=5)
    budget: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("purpose", "origin", "destination", "budget")
    @classmethod
    def one_line(cls, v):
        return _line(v)

    @field_validator("traveller_names", "notes")
    @classmethod
    def text(cls, v):
        return _text(v)

    @field_validator("needs")
    @classmethod
    def unique_needs(cls, v):
        return [c for c in CATEGORIES if c in v]

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.depart_date and self.return_date and self.return_date < self.depart_date:
            raise ValueError("The return date is before the departure date")
        return self


class StaffRequestIn(TripRequestIn):
    client_id: int


class OptionIn(BaseModel):
    category: Category
    title: str = Field(min_length=2, max_length=200)
    provider: str | None = Field(default=None, max_length=120)
    details: str | None = Field(default=None, max_length=2000)
    cost_price: Decimal | None = Field(default=None, ge=0, le=Decimal("100000000"), decimal_places=3)
    price: Decimal | None = Field(default=None, ge=0, le=Decimal("100000000"), decimal_places=3)

    @field_validator("title", "provider")
    @classmethod
    def one_line(cls, v):
        return _line(v)

    @field_validator("details")
    @classmethod
    def text(cls, v):
        return _text(v)


class VendorOptionIn(BaseModel):
    """A vendor gives its own price only."""

    category: Category
    title: str = Field(min_length=2, max_length=200)
    provider: str | None = Field(default=None, max_length=120)
    details: str | None = Field(default=None, max_length=2000)
    cost_price: Decimal = Field(ge=0, le=Decimal("100000000"), decimal_places=3)

    @field_validator("title", "provider")
    @classmethod
    def one_line(cls, v):
        return _line(v)

    @field_validator("details")
    @classmethod
    def text(cls, v):
        return _text(v)


class AssignVendorIn(BaseModel):
    vendor_id: int
    brief: str | None = Field(default=None, max_length=4000)

    @field_validator("brief")
    @classmethod
    def text(cls, v):
        return _text(v)


class SendToClientIn(BaseModel):
    option_ids: list[int] = Field(min_length=1, max_length=MAX_OPTIONS)


class ChooseIn(BaseModel):
    option_ids: list[int] = Field(min_length=1, max_length=5)


class MarkupIn(BaseModel):
    markup_percent: Decimal = Field(ge=0, le=500, decimal_places=2)


class BookedIn(BaseModel):
    booking_reference: str = Field(min_length=2, max_length=200)
    booking_notes: str | None = Field(default=None, max_length=4000)

    @field_validator("booking_reference")
    @classmethod
    def one_line(cls, v):
        return _line(v)

    @field_validator("booking_notes")
    @classmethod
    def text(cls, v):
        return _text(v)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    thread: Literal["client", "vendor"] | None = None  # staff only: which side

    @field_validator("text")
    @classmethod
    def clean(cls, v):
        v = _text(v)
        if not v:
            raise ValueError("Write a message")
        return v


class ReasonIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


# --- Views --------------------------------------------------------------------------------------------

class MessageOut(BaseModel):
    id: int
    thread: str
    author_kind: str
    author_name: str | None
    text: str
    created_at: datetime


class StepOut(BaseModel):
    action: str
    created_at: datetime


class EventOut(StepOut):
    actor_kind: str
    actor_name: str | None
    detail: str | None


class StaffOptionOut(BaseModel):
    id: int
    category: str
    title: str
    provider: str | None
    details: str | None
    cost_price: Decimal | None
    price: Decimal | None
    added_by: str
    sent_to_client: bool
    chosen: bool


class ClientOptionOut(BaseModel):
    id: int
    category: str
    title: str
    provider: str | None
    details: str | None
    price: Decimal | None
    chosen: bool


class VendorOptionOut(BaseModel):
    id: int
    category: str
    title: str
    provider: str | None
    details: str | None
    cost_price: Decimal | None
    chosen: bool  # shown once the request is approved


class TripCommon(BaseModel):
    id: int
    reference: str
    status: str
    purpose: str | None
    origin: str | None
    destination: str
    depart_date: date | None
    return_date: date | None
    travellers: int
    needs: list[str]
    created_at: datetime
    updated_at: datetime
    currency: str


class StaffTripOut(TripCommon):
    source: str
    client_id: int
    client_name: str
    vendor_id: int | None
    vendor_name: str | None
    vendor_accepted: bool | None
    traveller_names: str | None
    budget: str | None
    notes: str | None
    vendor_brief: str | None
    markup_percent: Decimal
    booking_reference: str | None
    booking_notes: str | None
    total_price: Decimal | None
    total_cost: Decimal | None
    options: list[StaffOptionOut]
    events: list[EventOut]
    messages: list[MessageOut]


class StaffTripRow(BaseModel):
    id: int
    reference: str
    status: str
    source: str
    client_name: str
    vendor_name: str | None
    destination: str
    depart_date: date | None
    travellers: int
    updated_at: datetime


class ClientTripOut(TripCommon):
    traveller_names: str | None
    budget: str | None
    notes: str | None
    booking_reference: str | None
    total_price: Decimal | None
    options: list[ClientOptionOut]
    steps: list[StepOut]
    messages: list[MessageOut]


class VendorTripOut(TripCommon):
    brief: str | None
    traveller_names: str | None  # after approval only
    accepted: bool | None
    booking_reference: str | None
    booking_notes: str | None
    total_cost: Decimal | None
    options: list[VendorOptionOut]
    steps: list[StepOut]
    messages: list[MessageOut]
