import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    STAFF = "staff"
    VIEWER = "viewer"


class QuoteStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONVERTED = "converted"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    CARD = "card"
    EFT = "eft"
    OTHER = "other"


class DealStage(str, enum.Enum):
    """One fixed pipeline, Pipedrive-style: open stages in order, then the
    two closed outcomes. Order here is display order on the board."""

    LEAD = "lead"
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"


# Industry of a deal: stable codes, labelled per language by the frontend.
INDUSTRIES = (
    "agriculture",
    "automotive",
    "construction",
    "education",
    "energy",
    "financial_services",
    "food_beverage",
    "government",
    "healthcare",
    "hospitality",
    "insurance",
    "it_software",
    "legal",
    "manufacturing",
    "media_marketing",
    "mining",
    "non_profit",
    "professional_services",
    "real_estate",
    "retail",
    "telecoms",
    "transport_logistics",
    "wholesale",
    "other",
)

OPEN_DEAL_STAGES = (DealStage.LEAD, DealStage.QUALIFIED, DealStage.PROPOSAL, DealStage.NEGOTIATION)


class ActivityType(str, enum.Enum):
    CALL = "call"
    MEETING = "meeting"
    TASK = "task"
    EMAIL = "email"
    DEADLINE = "deadline"


# South Africa's 11 official spoken languages, by ISO 639 code. The order
# is the display order in the language picker.
SUPPORTED_LANGUAGES = ("en", "af", "zu", "xh", "nso", "tn", "st", "ts", "ss", "ve", "nr")
