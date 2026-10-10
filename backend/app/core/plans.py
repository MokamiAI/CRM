"""YGT's subscription plans: prices, limits and what each one unlocks.

There is no free plan: every company starts with a free trial of Grow,
and once it ends (or a paid plan lapses) the company is read-only until
someone chooses a plan. Nothing is deleted.

Prices are in cents (ZAR). Annual billing charges ten months for twelve.
Every plan includes all 11 languages, email conversations, quotes,
invoices and payment reminders; the limits and features below are the
only differences."""
from dataclasses import dataclass, field

# Features a plan can unlock. Anything not listed here is in every plan.
WHATSAPP_SMS = "whatsapp_sms"
MARKETING = "marketing"
CUSTOM_FIELDS = "custom_fields"
TEAM_CHAT = "team_chat"
PRIORITY_SUPPORT = "priority_support"

INTERVALS = ("monthly", "annually")


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    monthly_cents: int  # per company, or per user when per_user
    per_user: bool = False
    min_users: int = 1
    max_users: int | None = None  # None: as many as are paid for
    max_customers: int | None = None
    invoices_per_month: int | None = None
    features: frozenset[str] = field(default_factory=frozenset)

    @property
    def paid(self) -> bool:
        return self.monthly_cents > 0

    def price_cents(self, interval: str, users: int = 1) -> int:
        months = 10 if interval == "annually" else 1
        return self.monthly_cents * months * (users if self.per_user else 1)

    def user_limit(self, seats: int) -> int | None:
        return seats if self.per_user else self.max_users


GROW_FEATURES = frozenset({WHATSAPP_SMS, MARKETING, CUSTOM_FIELDS, TEAM_CHAT})

PLANS: dict[str, Plan] = {
    "hustle": Plan("hustle", "Hustle", 19_900, max_users=3),
    "grow": Plan("grow", "Grow", 14_900, per_user=True, min_users=3, features=GROW_FEATURES),
    "scale": Plan("scale", "Scale", 24_900, per_user=True, min_users=3, features=GROW_FEATURES | {PRIORITY_SUPPORT}),
}
PAID_PLANS = list(PLANS.values())

# No trial or paid plan running: everything can be viewed, nothing added or sent.
LOCKED = Plan("none", "No plan", 0)

# During the free trial a company gets Grow, for up to this many people.
TRIAL_PLAN = "grow"
TRIAL_USERS = 10
# Days a lapsed payment keeps working while Paystack retries the card.
GRACE_DAYS = 3
