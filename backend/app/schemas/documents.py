"""How a company's invoices, quotes and statements look: set in Settings >
Documents, used for the printable documents and the emails."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

_text = lambda n: Field(default=None, max_length=n)  # noqa: E731


class DocumentTemplate(BaseModel):
    layout: Literal["modern", "classic", "minimal"] = "modern"
    accent: str = Field(default="#4f46e5", pattern=r"^#[0-9a-fA-F]{6}$")
    invoice_title: str = Field(default="Tax invoice", min_length=1, max_length=40)
    quote_title: str = Field(default="Quotation", min_length=1, max_length=40)
    statement_title: str = Field(default="Statement", min_length=1, max_length=40)
    # South Africa: "VAT number". The company's number is its tax number in
    # Settings > General; a client's is on their record.
    tax_label: str = Field(default="VAT number", min_length=1, max_length=30)
    show_logo: bool = True
    show_customer_tax_number: bool = True
    registration_number: str | None = _text(60)
    # Where to pay (shown on invoices and statements).
    bank_name: str | None = _text(80)
    account_holder: str | None = _text(120)
    account_number: str | None = _text(40)
    branch_code: str | None = _text(20)
    account_type: str | None = _text(40)
    swift_code: str | None = _text(20)
    payment_reference: str | None = Field(default="Please use the invoice number as your payment reference.", max_length=200)
    invoice_terms: str | None = _text(2000)
    quote_terms: str | None = _text(2000)
    footer: str | None = _text(300)

    @property
    def has_bank_details(self) -> bool:
        return any([self.bank_name, self.account_number])


def resolve_template(company) -> DocumentTemplate:
    """The company's saved choices over the defaults."""
    return DocumentTemplate.model_validate(company.document_template or {})


class PreviewRequest(BaseModel):
    template: DocumentTemplate
    kind: Literal["invoice", "quote", "statement"] = "invoice"


class StatementLine(BaseModel):
    date: date
    kind: Literal["invoice", "payment"]
    reference: str
    description: str
    debit: float = 0
    credit: float = 0
    balance: float


class Ageing(BaseModel):
    current: float
    days_30: float
    days_60: float
    days_90: float
    days_120: float  # more than 90 days overdue


class StatementOut(BaseModel):
    customer_id: str
    customer_name: str
    start: date
    end: date
    opening_balance: float
    invoiced: float
    paid: float
    closing_balance: float
    lines: list[StatementLine]
    ageing: Ageing


class StatementSend(BaseModel):
    start: date
    end: date
