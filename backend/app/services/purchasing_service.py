"""Suppliers, purchase orders and saved line templates."""
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import PurchaseOrderStatus
from app.models.purchasing import LineTemplate, PurchaseOrder, PurchaseOrderItem, Supplier
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.purchasing import LineTemplateCreate, PurchaseOrderCreate, PurchaseOrderUpdate, SupplierCreate, SupplierUpdate
from app.services.pricing import build_line_items

_ALLOWED: dict[PurchaseOrderStatus, set[PurchaseOrderStatus]] = {
    PurchaseOrderStatus.DRAFT: {PurchaseOrderStatus.SENT, PurchaseOrderStatus.CANCELLED},
    PurchaseOrderStatus.SENT: {PurchaseOrderStatus.RECEIVED, PurchaseOrderStatus.CANCELLED},
    PurchaseOrderStatus.RECEIVED: set(),
    PurchaseOrderStatus.CANCELLED: set(),
}


def _clean(value):
    return value.strip() or None if isinstance(value, str) else value


class SupplierService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, search: str | None = None, include_inactive: bool = False) -> list[Supplier]:
        query = select(Supplier).order_by(func.lower(Supplier.name))
        if not include_inactive:
            query = query.where(Supplier.is_active.is_(True))
        if search:
            like = f"%{search.strip()}%"
            query = query.where(or_(Supplier.name.ilike(like), Supplier.contact_name.ilike(like), Supplier.email.ilike(like)))
        return list(await self.db.scalars(query))

    async def get(self, supplier_id: uuid.UUID) -> Supplier:
        supplier = await self.db.get(Supplier, supplier_id)
        if supplier is None:
            raise NotFoundError("Supplier not found", "SUPPLIER_NOT_FOUND")
        return supplier

    async def create(self, data: SupplierCreate) -> Supplier:
        supplier = Supplier(**{k: _clean(v) for k, v in data.model_dump().items()})
        supplier.name = data.name.strip()
        self.db.add(supplier)
        await self.db.flush()
        return supplier

    async def update(self, supplier_id: uuid.UUID, data: SupplierUpdate) -> Supplier:
        supplier = await self.get(supplier_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(supplier, field, _clean(value))
        await self.db.flush()
        return supplier


class PurchaseOrderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _query(self):
        return select(PurchaseOrder).options(selectinload(PurchaseOrder.items))

    async def list(self, status: PurchaseOrderStatus | None = None, supplier_id: uuid.UUID | None = None, offset: int = 0, limit: int = 50) -> list[PurchaseOrder]:
        query = self._query().order_by(PurchaseOrder.created_at.desc()).offset(offset).limit(limit)
        if status:
            query = query.where(PurchaseOrder.status == status)
        if supplier_id:
            query = query.where(PurchaseOrder.supplier_id == supplier_id)
        return list(await self.db.scalars(query))

    async def get(self, po_id: uuid.UUID) -> PurchaseOrder:
        po = await self.db.scalar(self._query().where(PurchaseOrder.id == po_id))
        if po is None:
            raise NotFoundError("Purchase order not found", "PURCHASE_ORDER_NOT_FOUND")
        return po

    async def _active_supplier(self, supplier_id: uuid.UUID) -> Supplier:
        supplier = await self.db.get(Supplier, supplier_id)
        if supplier is None or not supplier.is_active:
            raise NotFoundError("Supplier not found or inactive", "SUPPLIER_NOT_FOUND")
        return supplier

    async def create(self, data: PurchaseOrderCreate, created_by: uuid.UUID) -> PurchaseOrder:
        await self._active_supplier(data.supplier_id)
        items, subtotal, tax_total, total = build_line_items(PurchaseOrderItem, data.items)
        po = PurchaseOrder(
            po_number=await CompanySettingsRepository(self.db).reserve_next_po_number(),
            supplier_id=data.supplier_id,
            issue_date=data.issue_date,
            delivery_date=data.delivery_date,
            delivery_address=_clean(data.delivery_address),
            reference=_clean(data.reference),
            notes=_clean(data.notes),
            subtotal=subtotal,
            tax_total=tax_total,
            total=total,
            created_by=created_by,
            items=items,
        )
        self.db.add(po)
        await self.db.flush()
        return await self.get(po.id)

    async def update(self, po_id: uuid.UUID, data: PurchaseOrderUpdate) -> PurchaseOrder:
        po = await self.get(po_id)
        if po.status != PurchaseOrderStatus.DRAFT:
            raise ConflictError("Only draft purchase orders can be edited", "PURCHASE_ORDER_NOT_EDITABLE")
        changes = data.model_dump(exclude_unset=True, exclude={"items"})
        if "supplier_id" in changes and changes["supplier_id"]:
            await self._active_supplier(changes["supplier_id"])
        for field, value in changes.items():
            setattr(po, field, _clean(value))
        if data.items is not None:
            items, subtotal, tax_total, total = build_line_items(PurchaseOrderItem, data.items)
            po.items.clear()
            po.items.extend(items)
            po.subtotal, po.tax_total, po.total = subtotal, tax_total, total
        await self.db.flush()
        return await self.get(po.id)

    async def transition(self, po_id: uuid.UUID, new_status: PurchaseOrderStatus) -> PurchaseOrder:
        po = await self.get(po_id)
        if new_status not in _ALLOWED[po.status]:
            raise ConflictError(f"Can't move a {po.status.value} purchase order to {new_status.value}", "PURCHASE_ORDER_INVALID_TRANSITION")
        po.status = new_status
        await self.db.flush()
        return po

    async def delete(self, po_id: uuid.UUID) -> None:
        po = await self.get(po_id)
        if po.status != PurchaseOrderStatus.DRAFT:
            raise ConflictError("Only draft purchase orders can be deleted", "PURCHASE_ORDER_NOT_DELETABLE")
        await self.db.delete(po)
        await self.db.flush()


class LineTemplateService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self) -> list[LineTemplate]:
        return list(await self.db.scalars(select(LineTemplate).order_by(func.lower(LineTemplate.name))))

    async def create(self, data: LineTemplateCreate, created_by: uuid.UUID) -> LineTemplate:
        name = data.name.strip()
        existing = await self.db.scalar(select(LineTemplate).where(func.lower(LineTemplate.name) == name.lower()))
        items = [item.model_dump(mode="json") for item in data.items]
        if existing:  # saving under the same name replaces it
            existing.items = items
            await self.db.flush()
            return existing
        template = LineTemplate(name=name, items=items, created_by=created_by)
        self.db.add(template)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise ConflictError("A saved set with that name already exists", "LINE_TEMPLATE_EXISTS") from exc
        return template

    async def delete(self, template_id: uuid.UUID) -> None:
        template = await self.db.get(LineTemplate, template_id)
        if template is None:
            raise NotFoundError("Saved items not found", "LINE_TEMPLATE_NOT_FOUND")
        await self.db.delete(template)
        await self.db.flush()
