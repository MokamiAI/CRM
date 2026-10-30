"""YGT's own sales pipeline, kept up to date from sign-ups and subscriptions.

Every company that signs up to YGT becomes a prospect in YGT's workspace
(the company of the first platform admin), with every stage on record:

    signs up (trial)   deal at Negotiation, closing when the trial ends;
                       a quote for their plan and seats, Accepted (they saw
                       the price when they chose it); an R0.00 invoice for
                       the trial (the price, less a free-trial discount of
                       the same amount), emailed to them
    during the trial   quote and trial invoice follow the seats in use
    pays               deal Won, the prospect becomes a customer; each
                       Paystack (or bank transfer) payment is a paid invoice
                       under a monthly recurring invoice. Paystack bills
                       them, so these are records, never emailed
    doesn't pay        deal back to Proposal; the recurring invoice stops

The deal moves only when the subscription state changes
(SubscriberLink.state), so a stage set by hand stays until the subscriber's
situation actually changes; a deal deleted by hand is not recreated.
Runs every few minutes (billing_tasks).
"""
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import func, select

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.plans import PLANS, TRIAL_PLAN, Plan
from app.core.tenancy import set_system, set_tenant
from app.models.billing import BillingPayment, SubscriberLink, Subscription
from app.models.company_settings import CompanySettings
from app.models.crm import Deal
from app.models.customer import Customer
from app.models.enums import DealStage, InvoiceStatus, PaymentMethod, QuoteStatus, UserRole
from app.models.invoice import Invoice, InvoiceItem
from app.models.quote import Quote, QuoteItem
from app.models.recurring import RecurringInvoice
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.crm import DealCreate, DealUpdate
from app.schemas.customer import ContactPerson, CustomerCreate
from app.schemas.payment import PaymentCreate
from app.services.billing_service import _add_interval, effective
from app.services.customer_service import CustomerService
from app.services.deal_service import DealService
from app.services.payment_service import PaymentService
from app.services.pricing import build_line_items
from app.services.recurring_service import next_cycle

logger = logging.getLogger(__name__)

STAGES = {
    "trialing": DealStage.NEGOTIATION,
    "trial_grace": DealStage.NEGOTIATION,  # trial over, a few days left to pay
    "active": DealStage.WON,
    "past_due": DealStage.WON,
    "cancelled": DealStage.PROPOSAL,
    "trial_ended": DealStage.PROPOSAL,
    "lapsed": DealStage.PROPOSAL,
}
ON_TRIAL = ("trialing", "trial_grace")
PAYING = ("active", "past_due")


@dataclass
class Change:
    company: str
    action: str  # add | move | seats | paid
    state: str
    stage: DealStage
    plan: str
    seats: int
    value: Decimal
    close: date | None
    detail: str = ""
    email_invoice_id: object = field(default=None, repr=False)  # the trial invoice to email after commit


async def workspace(db) -> tuple[CompanySettings | None, User | None]:
    """YGT's own company and the admin whose deals these are: the first
    platform admin with a confirmed email."""
    if not settings.platform_admins:
        return None, None
    users = await db.scalars(select(User).where(func.lower(User.email).in_(settings.platform_admins), User.is_active.is_(True)).order_by(User.created_at))
    admin = next((u for u in users if u.is_platform_admin), None)
    return (await db.get(CompanySettings, admin.company_id), admin) if admin else (None, None)


def _money(cents: int) -> Decimal:
    return Decimal(cents) / 100


def _plan_line(plan: Plan, seats: int) -> SimpleNamespace:
    """One month of the plan for this many seats, as a line item."""
    if plan.per_user:
        return _line(f"YGT {plan.name} plan, per seat per month", seats, _money(plan.seat_cents(seats)))
    return _line(f"YGT {plan.name} plan, per month (up to {plan.max_users} people)", 1, _money(plan.monthly_cents))


def _line(description: str, quantity, unit_price: Decimal) -> SimpleNamespace:
    # Not the API's line-item schema: the free-trial discount is a negative
    # line, which only YGT's own documents may have.
    return SimpleNamespace(product_id=None, description=description, quantity=Decimal(quantity), unit_price=unit_price, tax_rate=Decimal("0"))


async def sync(db, apply: bool = True, only: set | None = None) -> list[Change]:
    """Brings YGT's pipeline up to date; returns what changed (or, with
    apply=False, what would). `only`: just these company ids. The caller
    commits, then emails each change's email_invoice_id."""
    set_system(db)
    ygt, admin = await workspace(db)
    if ygt is None:
        return []
    links = {link.company_id: link for link in await db.scalars(select(SubscriberLink))}
    subs = {sub.company_id: sub for sub in await db.scalars(select(Subscription))}
    owners, people = {}, {}
    for user in await db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.created_at)):
        people[user.company_id] = people.get(user.company_id, 0) + 1
        if user.role == UserRole.ADMIN:
            owners.setdefault(user.company_id, user)
    known = {name.strip().lower(): cid for cid, name in await db.execute(
        select(Customer.id, Customer.name).where(Customer.company_id == ygt.id).order_by(Customer.created_at))}
    recorded = set(await db.scalars(select(Invoice.reference).where(Invoice.company_id == ygt.id, Invoice.reference.is_not(None))))
    payments = {}
    for payment in await db.scalars(select(BillingPayment).order_by(BillingPayment.paid_at)):
        if payment.reference not in recorded:
            payments.setdefault(payment.company_id, []).append(payment)

    work = []
    for company in await db.scalars(select(CompanySettings).where(CompanySettings.id != ygt.id).order_by(CompanySettings.created_at)):
        sub = subs.get(company.id)
        if sub is None or (only is not None and company.id not in only):
            continue
        state = effective(sub).state
        link = links.get(company.id)
        plan = PLANS.get(sub.plan) or PLANS[TRIAL_PLAN]
        on_trial = state in ON_TRIAL
        seats = max(people.get(company.id, 1), 1) if on_trial else max(sub.seats or 1, 1)
        close = sub.trial_ends_at.date() if on_trial and sub.trial_ends_at else None
        value = _money(plan.price_cents("monthly", seats))
        stage = STAGES.get(state, DealStage.PROPOSAL)

        def change(action, detail=""):
            return Change(company.company_name, action, state, stage, plan.name, seats, value, close, detail)

        todo = []
        if link is None:
            todo.append(change("add"))
        elif link.state != state:
            todo.append(change("move"))
        if on_trial and link is not None and link.quote_id is None:
            todo.append(change("documents", "quote and trial invoice"))
        elif on_trial and link is not None and link.seats != seats:
            todo.append(change("seats", f"{link.seats} -> {seats} seats"))
        todo += [change("paid", f"R{_money(p.amount_cents):,.2f} on {p.paid_at:%Y-%m-%d}") for p in payments.get(company.id, [])]
        if todo:
            work.append((company, sub, link, plan, seats, todo))
    if not apply:
        return [c for *_, todo in work for c in todo]

    set_tenant(db, ygt.id)  # every write below is in YGT's own workspace
    done = []
    for company, sub, link, plan, seats, todo in work:
        try:
            async with db.begin_nested():
                first = todo[0]  # state, stage and value are the same on every change
                fresh = link is None
                if fresh:
                    link = await _add(db, admin, company, owners.get(company.id), known.get(company.company_name.strip().lower()), first)
                elif link.state != first.state:
                    await _move(db, admin, link, first)
                if first.state in ON_TRIAL and (link.quote_id is None or link.seats != seats):
                    trial_invoice = await _trial_documents(db, admin, company, sub, link, plan, seats)
                    # Emailed once, when someone has just signed up.
                    if fresh and trial_invoice is not None:
                        first.email_invoice_id = trial_invoice.id
                for payment in payments.get(company.id, []):
                    await _record_payment(db, admin, link, payment, plan)
                if first.state not in PAYING and link.recurring_id:
                    schedule = await db.get(RecurringInvoice, link.recurring_id)
                    if schedule is not None:
                        schedule.active = False
                await db.flush()
            done += todo
        except Exception:
            logger.exception("Couldn't update YGT's pipeline for %s", company.company_name)
    await _sync_consent(db, owners, only)
    return done


async def _sync_consent(db, owners: dict, only: set | None) -> None:
    """Each subscriber's answer to YGT's marketing question (their owner's,
    from sign-up, the app or their profile) onto their record in YGT's
    workspace, so campaigns reach exactly those who said yes (POPIA s69).
    Only a newer answer counts: an unsubscribe from a campaign email since
    then stands."""
    links = await db.scalars(select(SubscriberLink).where(SubscriberLink.customer_id.is_not(None)))
    for link in links:
        owner = owners.get(link.company_id)
        if only is not None and link.company_id not in only:
            continue
        if owner is None or owner.marketing_opt_in is None or owner.marketing_opt_in_at is None:
            continue
        customer = await db.get(Customer, link.customer_id)
        if customer is None:
            continue
        latest = max((at for at in (customer.marketing_consent_at, customer.marketing_opt_out_at) if at), default=None)
        if latest is not None and latest >= owner.marketing_opt_in_at:
            continue
        if owner.marketing_opt_in:
            customer.marketing_consent_at = owner.marketing_opt_in_at
            customer.marketing_consent_source = f"Said yes in YGT ({owner.marketing_opt_in_source})"
            customer.marketing_opt_out = False
        else:
            customer.marketing_opt_out = True
            customer.marketing_opt_out_at = owner.marketing_opt_in_at
    await db.flush()


async def _add(db, admin: User, company: CompanySettings, owner: User | None, customer_id, change: Change) -> SubscriberLink:
    deal = None
    if customer_id is None:
        customer = await CustomerService(db).create_customer(
            CustomerCreate(
                name=company.company_name,
                email=owner.email if owner else None,
                billing_address=company.address,
                notes=f"Signed up to YGT on {company.created_at:%Y-%m-%d}.",
                contact=ContactPerson(name=owner.full_name, email=owner.email) if owner and owner.full_name.strip() else None,
            ),
            created_by=admin,
            is_prospect=True,
        )
        customer_id = customer.id
    else:
        # Already in YGT's workspace (added by hand): carry on with their latest deal.
        deal = await db.scalar(select(Deal).where(Deal.customer_id == customer_id).order_by(Deal.created_at.desc()).limit(1))
    if deal is None:
        deal = await DealService(db).create_deal(
            DealCreate(title=f"{company.company_name} · YGT {change.plan}", customer_id=customer_id, owner_id=admin.id,
                       stage=change.stage, value=change.value, expected_close_date=change.close),
            created_by_id=admin.id,
        )
    else:
        await _update_deal(db, admin, deal.id, change)
    link = SubscriberLink(company_id=company.id, customer_id=customer_id, deal_id=deal.id, state=change.state)
    db.add(link)
    await db.flush()
    return link


async def _move(db, admin: User, link: SubscriberLink, change: Change) -> None:
    if link.deal_id is not None and await db.get(Deal, link.deal_id) is not None:
        await _update_deal(db, admin, link.deal_id, change)
    link.state = change.state
    await db.flush()


async def _update_deal(db, admin: User, deal_id, change: Change) -> None:
    try:
        async with db.begin_nested():
            await DealService(db).update_deal(
                deal_id, DealUpdate(stage=change.stage, value=change.value, expected_close_date=change.close), actor_id=admin.id)
    except AppError as exc:
        # E.g. an MCEM deal that needs evidence before it can move: leave the
        # stage to whoever runs it, but remember the state so we don't retry.
        logger.warning("Left the deal for %s at its stage: %s", change.company, exc)


async def _trial_documents(db, admin: User, company: CompanySettings, sub: Subscription, link: SubscriberLink, plan: Plan, seats: int) -> Invoice | None:
    """The quote they accepted by choosing a plan, and the R0.00 invoice for
    the trial, at the seats in use now. Made once, then kept up to date."""
    if link.customer_id is None:
        return None
    start = sub.created_at.date()
    end = (sub.trial_ends_at or sub.created_at).date()
    days = max((end - start).days, 1)
    period = f"{start:%d %b %Y} to {end:%d %b %Y}"
    month = _plan_line(plan, seats)
    monthly = month.quantity * month.unit_price
    numbers = CompanySettingsRepository(db)

    quote = await db.get(Quote, link.quote_id) if link.quote_id else None
    items, subtotal, tax_total, total = build_line_items(QuoteItem, [month])
    if quote is None:
        quote = Quote(quote_number=await numbers.reserve_next_quote_number(), customer_id=link.customer_id, deal_id=link.deal_id,
                      status=QuoteStatus.ACCEPTED, issue_date=start, expiry_date=end, created_by=admin.id,
                      title=f"YGT {plan.name} subscription")
        db.add(quote)
    else:
        await db.refresh(quote, ["items"])
    quote.items, quote.subtotal, quote.tax_total, quote.total = items, subtotal, tax_total, total
    quote.notes = (f"Accepted when {company.company_name} chose YGT {plan.name} at sign-up: R{monthly:,.2f} a month for "
                   f"{seats} {'seat' if seats == 1 else 'seats'}, free for the first {days} days ({period}).")

    invoice = await db.get(Invoice, link.trial_invoice_id) if link.trial_invoice_id else None
    lines = [
        _line(f"{month.description}: {days}-day free trial, {period}", month.quantity, month.unit_price),
        _line(f"Free trial discount ({days} days)", 1, -monthly),
    ]
    items, subtotal, tax_total, total = build_line_items(InvoiceItem, lines)
    if invoice is None:
        invoice = Invoice(invoice_number=await numbers.reserve_next_invoice_number(), customer_id=link.customer_id,
                          status=InvoiceStatus.PAID, issue_date=start, due_date=start, amount_paid=Decimal("0"),
                          created_by=admin.id)
        db.add(invoice)
    else:
        await db.refresh(invoice, ["items"])
    invoice.items, invoice.subtotal, invoice.tax_total, invoice.total = items, subtotal, tax_total, total
    await db.flush()
    invoice.quote_id = quote.id
    invoice.notes = (f"Your {days}-day free trial of YGT {plan.name}, {period}: nothing to pay today. "
                     f"From {end:%d %b %Y} it's R{monthly:,.2f} a month, billed monthly by card through Paystack once you choose to subscribe.")
    link.quote_id, link.trial_invoice_id, link.seats = quote.id, invoice.id, seats
    deal = await db.get(Deal, link.deal_id) if link.deal_id else None
    if deal is not None:
        deal.value = monthly
    await db.flush()
    return invoice


async def _record_payment(db, admin: User, link: SubscriberLink, payment: BillingPayment, plan: Plan) -> None:
    """A subscription payment as a paid invoice under their monthly
    recurring invoice (made at the first payment). Paystack does the
    billing, so the recurring invoice is a record that is never emailed."""
    if link.customer_id is None:
        return
    plan = PLANS.get(payment.plan) or plan
    paid = payment.paid_at.date()
    end = _add_interval(payment.paid_at, payment.interval).date()
    amount = _money(payment.amount_cents)
    seats = max(payment.seats or 1, 1)
    description = (f"YGT {plan.name} plan, {seats} {'seat' if seats == 1 else 'seats'}, "
                   f"{'yearly' if payment.interval == 'annually' else 'monthly'}: {paid:%d %b %Y} to {end:%d %b %Y}")
    frequency = "yearly" if payment.interval == "annually" else "monthly"

    schedule = await db.get(RecurringInvoice, link.recurring_id) if link.recurring_id else None
    if schedule is None or schedule.frequency != frequency:
        schedule = RecurringInvoice(customer_id=link.customer_id, frequency=frequency, start_date=paid, next_run_date=paid,
                                    due_days=0, notes="Billed automatically by Paystack; recorded here when each payment arrives.",
                                    items=[], created_by=admin.id)
        db.add(schedule)
        await db.flush()
        link.recurring_id = schedule.id
    schedule.active = True
    schedule.items = [{"product_id": None, "description": f"YGT {plan.name} plan, {seats} {'seat' if seats == 1 else 'seats'}",
                       "quantity": "1", "unit_price": str(amount), "tax_rate": "0"}]

    items, subtotal, tax_total, total = build_line_items(InvoiceItem, [_line(description, 1, amount)])
    # A draft the recurring run already made for this cycle is used, not duplicated.
    invoice = await db.scalar(select(Invoice).where(Invoice.recurring_invoice_id == schedule.id, Invoice.status == InvoiceStatus.DRAFT)
                              .order_by(Invoice.recurrence_date).limit(1))
    if invoice is None:
        if schedule.next_run_date + timedelta(days=7) < paid:
            # Back after a gap: the cycle starts again from this payment, so
            # the recurring run doesn't fill the missed months with drafts.
            schedule.start_date = schedule.next_run_date = paid
        cycle = schedule.next_run_date
        invoice = Invoice(invoice_number=await CompanySettingsRepository(db).reserve_next_invoice_number(), customer_id=link.customer_id,
                          recurring_invoice_id=schedule.id, recurrence_date=cycle, created_by=admin.id)
        db.add(invoice)
        schedule.next_run_date = next_cycle(schedule, cycle)
    else:
        await db.refresh(invoice, ["items"])
    invoice.issue_date, invoice.due_date = paid, paid
    invoice.reference = payment.reference[:100]
    invoice.notes = "Paid by card through Paystack." if not payment.reference.startswith("manual:") else "Paid by bank transfer."
    invoice.items, invoice.subtotal, invoice.tax_total, invoice.total = items, subtotal, tax_total, total
    invoice.status, invoice.amount_paid = InvoiceStatus.SENT, Decimal("0")
    await db.flush()
    await PaymentService(db).record_payment(invoice.id, PaymentCreate(
        amount=total, method=PaymentMethod.BANK_TRANSFER if payment.reference.startswith("manual:") else PaymentMethod.CARD,
        reference=payment.reference[:255], paid_at=payment.paid_at), recorded_by_id=admin.id)
    if (customer := await db.get(Customer, link.customer_id)) is not None:
        customer.is_prospect = False
    await db.flush()
