from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol, TypeVar

CENT = Decimal("0.01")


class _LineItemData(Protocol):
    product_id: object
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal


class _LineItemModel(Protocol):
    def __init__(self, **kwargs) -> None: ...


M = TypeVar("M", bound=_LineItemModel)


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def build_line_items(
    model_cls: type[M], items_data: list[_LineItemData]
) -> tuple[list[M], Decimal, Decimal, Decimal]:
    """Builds ORM line-item rows from input data, computing each line's
    total and the document's subtotal/tax_total/total. Tax is calculated
    per line (not on the summed subtotal) so per-line tax rates are
    respected, then rounded half-up to the cent at each step to avoid
    drift between the stored line totals and the document total."""
    items: list[M] = []
    subtotal = Decimal("0")
    tax_total = Decimal("0")
    for sort_order, item in enumerate(items_data):
        line_total = money(item.quantity * item.unit_price)
        line_tax = money(line_total * item.tax_rate / Decimal("100"))
        items.append(
            model_cls(
                product_id=item.product_id,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                tax_rate=item.tax_rate,
                line_total=line_total,
                sort_order=sort_order,
            )
        )
        subtotal += line_total
        tax_total += line_tax
    return items, subtotal, tax_total, subtotal + tax_total
