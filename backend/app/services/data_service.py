"""Moving in and out: CSV import of clients (with a contact), products and
deals, and CSV export of everything a company has. The browser reads the
file and matches its columns to YGT's fields; rows arrive here as
{field: text} and are checked one by one, so one bad row never stops
the rest."""
import csv
import io
import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.tenancy import current_company_id
from app.models.crm import Contact, Deal
from app.models.customer import Customer
from app.models.enums import DealStage
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.product import Product
from app.models.quote import Quote
from app.models.user import User

MAX_ROWS = 5000

# What each import understands; the first ones are required.
FIELDS = {
    "customers": {
        "required": ["name"],
        "optional": ["email", "phone", "billing_address", "tax_number", "notes",
                     "contact_first_name", "contact_last_name", "contact_email", "contact_phone", "contact_job_title"],
    },
    "products": {"required": ["name", "unit_price"], "optional": ["sku", "tax_rate", "description"]},
    "deals": {"required": ["title", "customer"], "optional": ["value", "stage", "expected_close_date", "industry", "owner_email"]},
}


class RowError(ValueError):
    pass


def _text(row: dict, key: str, limit: int) -> str | None:
    value = (row.get(key) or "").strip()
    return value[:limit] if value else None


def _money(value: str | None, field: str) -> Decimal | None:
    """'R 1 234,50', '1,234.50', '1234.5' -> Decimal."""
    if value is None or not str(value).strip():
        return None
    raw = re.sub(r"[^\d,.\-]", "", str(value))
    if "," in raw and "." in raw:
        raw = raw.replace(",", "") if raw.rfind(".") > raw.rfind(",") else raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".") if len(raw.split(",")[-1]) in (1, 2) else raw.replace(",", "")
    try:
        number = Decimal(raw)
    except InvalidOperation:
        raise RowError(f"{field} isn't a number: {value}")
    if number < 0:
        raise RowError(f"{field} can't be negative")
    return number.quantize(Decimal("0.01"))


def _date(value: str | None) -> date | None:
    if not value or not value.strip():
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise RowError(f"Couldn't read the date {value!r} (use 2026-10-31 or 31/10/2026)")


def _stage(value: str | None) -> DealStage:
    if not value or not value.strip():
        return DealStage.LEAD
    key = value.strip().lower().replace(" ", "_")
    for stage in DealStage:
        if key in (stage.value, stage.name.lower()):
            return stage
    raise RowError(f"Unknown stage {value!r} (use lead, qualified, proposal, negotiation, won or lost)")


def _email(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    value = value.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise RowError(f"{value!r} isn't an email address")
    return value


class ImportService:
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user
        self.company_id = current_company_id(db)

    async def run(self, entity: str, rows: list[dict], update_existing: bool) -> dict:
        if entity not in FIELDS:
            raise AppError("Unknown import", "IMPORT_UNKNOWN")
        if len(rows) > MAX_ROWS:
            raise AppError(f"Import at most {MAX_ROWS} rows at a time", "IMPORT_TOO_MANY_ROWS")
        result = {"created": 0, "updated": 0, "skipped": 0, "errors": []}
        handler = getattr(self, f"_{entity}")
        await self._prepare(entity)
        for number, row in enumerate(rows, start=2):  # row 1 is the header in the file
            try:
                async with self.db.begin_nested():
                    outcome = await handler({k: (str(v) if v is not None else "") for k, v in row.items()}, update_existing)
                result[outcome] += 1
            except RowError as exc:
                result["errors"].append({"row": number, "message": str(exc)})
            except Exception as exc:  # a database error on one row
                result["errors"].append({"row": number, "message": f"Couldn't save this row ({type(exc).__name__})"})
        await self.db.flush()
        result["errors"] = result["errors"][:200]
        return result

    async def _prepare(self, entity: str) -> None:
        customers = list(await self.db.scalars(select(Customer)))
        self.customers_by_email = {c.email.lower(): c for c in customers if c.email}
        self.customers_by_name = {c.name.casefold(): c for c in customers}
        if entity == "products":
            products = list(await self.db.scalars(select(Product)))
            self.products_by_sku = {p.sku.casefold(): p for p in products if p.sku}
            self.products_by_name = {p.name.casefold(): p for p in products}
        if entity == "deals":
            self.users_by_email = {u.email.lower(): u for u in await self.db.scalars(select(User))}
            self.deals = {(d.title.casefold(), d.customer_id): d for d in await self.db.scalars(select(Deal))}

    async def _customers(self, row: dict, update_existing: bool) -> str:
        name = _text(row, "name", 255)
        if not name:
            raise RowError("Name is missing")
        email = _email(row.get("email"))
        existing = (self.customers_by_email.get(email) if email else None) or self.customers_by_name.get(name.casefold())
        fields = {
            "name": name, "email": email, "phone": _text(row, "phone", 50), "billing_address": _text(row, "billing_address", 2000),
            "tax_number": _text(row, "tax_number", 100), "notes": _text(row, "notes", 5000),
        }
        if existing:
            if not update_existing:
                return "skipped"
            for key, value in fields.items():
                if value is not None:
                    setattr(existing, key, value)
            customer, outcome = existing, "updated"
        else:
            customer = Customer(company_id=self.company_id, created_by=self.user.id, **fields)
            self.db.add(customer)
            await self.db.flush()
            outcome = "created"
        self.customers_by_name[customer.name.casefold()] = customer
        if customer.email:
            self.customers_by_email[customer.email.lower()] = customer
        first = _text(row, "contact_first_name", 120)
        contact_email = _email(row.get("contact_email"))
        if first or contact_email:
            known = contact_email and await self.db.scalar(select(Contact.id).where(Contact.customer_id == customer.id, Contact.email == contact_email))
            if not known:
                has_primary = await self.db.scalar(select(Contact.id).where(Contact.customer_id == customer.id, Contact.is_primary.is_(True)))
                self.db.add(
                    Contact(
                        company_id=self.company_id, customer_id=customer.id, first_name=first or contact_email.split("@")[0],
                        last_name=_text(row, "contact_last_name", 120), email=contact_email, phone=_text(row, "contact_phone", 50),
                        job_title=_text(row, "contact_job_title", 120), is_primary=not has_primary,
                    )
                )
        return outcome

    async def _products(self, row: dict, update_existing: bool) -> str:
        name = _text(row, "name", 255)
        if not name:
            raise RowError("Name is missing")
        price = _money(row.get("unit_price"), "Price")
        if price is None:
            raise RowError("Price is missing")
        tax = _money(row.get("tax_rate"), "VAT rate")
        if tax is not None and tax > 100:
            raise RowError("VAT rate must be a percentage, e.g. 15")
        sku = _text(row, "sku", 100)
        existing = (self.products_by_sku.get(sku.casefold()) if sku else None) or self.products_by_name.get(name.casefold())
        fields = {"name": name, "sku": sku, "unit_price": price, "tax_rate": tax if tax is not None else Decimal("15"), "description": _text(row, "description", 5000)}
        if existing:
            if not update_existing:
                return "skipped"
            for key, value in fields.items():
                if value is not None:
                    setattr(existing, key, value)
            return "updated"
        product = Product(company_id=self.company_id, **fields)
        self.db.add(product)
        self.products_by_name[name.casefold()] = product
        if sku:
            self.products_by_sku[sku.casefold()] = product
        return "created"

    async def _deals(self, row: dict, update_existing: bool) -> str:
        title = _text(row, "title", 255)
        if not title:
            raise RowError("Deal name is missing")
        customer_name = _text(row, "customer", 255)
        if not customer_name:
            raise RowError("Client is missing")
        customer = self.customers_by_name.get(customer_name.casefold())
        if customer is None:  # new client, created with the deal
            customer = Customer(company_id=self.company_id, name=customer_name, created_by=self.user.id)
            self.db.add(customer)
            await self.db.flush()
            self.customers_by_name[customer_name.casefold()] = customer
        owner_email = _email(row.get("owner_email"))
        owner = self.users_by_email.get(owner_email) if owner_email else None
        if owner_email and owner is None:
            raise RowError(f"No one on your team has the email {owner_email}")
        stage = _stage(row.get("stage"))
        fields = {
            "value": _money(row.get("value"), "Value") or Decimal("0"),
            "stage": stage,
            "expected_close_date": _date(row.get("expected_close_date")),
            "industry": _text(row, "industry", 40),
            "owner_id": (owner or self.user).id,
        }
        existing = self.deals.get((title.casefold(), customer.id))
        if existing:
            if not update_existing:
                return "skipped"
            for key, value in fields.items():
                if value is not None:
                    setattr(existing, key, value)
            return "updated"
        deal = Deal(company_id=self.company_id, title=title, customer_id=customer.id, created_by=self.user.id, **fields)
        if stage in (DealStage.WON, DealStage.LOST):
            deal.closed_at = datetime.now().astimezone()
        self.db.add(deal)
        self.deals[(title.casefold(), customer.id)] = deal
        return "created"


# ---------------------------------------------------------------- export

EXPORTS = ("customers", "contacts", "products", "deals", "invoices", "quotes", "payments")


def _fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value"):  # enums
        return str(value.value)
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", chr(9), chr(13)):
        # Text from customers (names arriving by WhatsApp or email) must not
        # run as a formula when the export is opened in Excel.
        return "'" + value
    return str(value)


async def export_csv(db: AsyncSession, entity: str) -> str:
    """A CSV Excel opens correctly (UTF-8 with a byte order mark)."""
    if entity not in EXPORTS:
        raise AppError("Unknown export", "EXPORT_UNKNOWN")
    names = {c.id: c.name for c in await db.scalars(select(Customer))}
    out = io.StringIO()
    out.write("﻿")
    writer = csv.writer(out)

    def rows(header, items, pick):
        writer.writerow(header)
        for item in items:
            writer.writerow([_fmt(v) for v in pick(item)])

    if entity == "customers":
        rows(["name", "email", "phone", "billing_address", "tax_number", "notes", "active", "created_at"],
             await db.scalars(select(Customer).order_by(Customer.name)),
             lambda c: [c.name, c.email, c.phone, c.billing_address, c.tax_number, c.notes, c.is_active, c.created_at])
    elif entity == "contacts":
        rows(["customer", "first_name", "last_name", "email", "phone", "job_title", "primary"],
             await db.scalars(select(Contact).order_by(Contact.customer_id)),
             lambda c: [names.get(c.customer_id), c.first_name, c.last_name, c.email, c.phone, c.job_title, c.is_primary])
    elif entity == "products":
        rows(["name", "sku", "unit_price", "tax_rate", "description", "active"],
             await db.scalars(select(Product).order_by(Product.name)),
             lambda p: [p.name, p.sku, p.unit_price, p.tax_rate, p.description, p.is_active])
    elif entity == "deals":
        owners = {u.id: u.email for u in await db.scalars(select(User))}
        rows(["title", "customer", "value", "stage", "expected_close_date", "industry", "owner_email", "created_at", "closed_at"],
             await db.scalars(select(Deal).order_by(Deal.created_at)),
             lambda d: [d.title, names.get(d.customer_id), d.value, d.stage, d.expected_close_date, d.industry, owners.get(d.owner_id), d.created_at, d.closed_at])
    elif entity == "invoices":
        rows(["number", "customer", "po_number", "reference", "status", "issue_date", "due_date", "subtotal", "vat", "total", "paid", "balance"],
             await db.scalars(select(Invoice).order_by(Invoice.issue_date)),
             lambda i: [i.invoice_number, names.get(i.customer_id), i.po_number, i.reference, i.status, i.issue_date, i.due_date, i.subtotal, i.tax_total, i.total, i.amount_paid, Decimal(str(i.total)) - Decimal(str(i.amount_paid))])
    elif entity == "quotes":
        rows(["number", "customer", "po_number", "reference", "status", "issue_date", "valid_until", "subtotal", "vat", "total"],
             await db.scalars(select(Quote).order_by(Quote.issue_date)),
             lambda q: [q.quote_number, names.get(q.customer_id), q.po_number, q.reference, q.status, q.issue_date, q.expiry_date, q.subtotal, q.tax_total, q.total])
    elif entity == "payments":
        numbers = {i.id: (i.invoice_number, names.get(i.customer_id)) for i in await db.scalars(select(Invoice))}
        rows(["invoice", "customer", "amount", "method", "reference", "paid_at"],
             await db.scalars(select(Payment).order_by(Payment.paid_at)),
             lambda p: [numbers.get(p.invoice_id, ("", ""))[0], numbers.get(p.invoice_id, ("", ""))[1], p.amount, p.method, p.reference, p.paid_at])
    return out.getvalue()
