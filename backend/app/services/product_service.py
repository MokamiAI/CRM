import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.product import Product
from app.repositories.product_repository import ProductRepository
from app.schemas.product import ProductCreate, ProductUpdate


class ProductService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.products = ProductRepository(db)

    async def _ensure_sku_free(self, sku: str | None, exclude_id: uuid.UUID | None = None) -> None:
        if sku is None:
            return
        existing = await self.products.get_by_sku(sku)
        if existing is not None and existing.id != exclude_id:
            raise ConflictError("A product with this SKU already exists", "PRODUCT_SKU_TAKEN")

    async def create_product(self, data: ProductCreate) -> Product:
        await self._ensure_sku_free(data.sku)
        product = Product(
            name=data.name,
            description=data.description,
            sku=data.sku,
            unit_price=data.unit_price,
            tax_rate=data.tax_rate,
        )
        return await self.products.create(product)

    async def list_products(
        self,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> list[Product]:
        return await self.products.list_all(
            offset=offset, limit=limit, search=search, is_active=is_active
        )

    async def get_product(self, product_id: uuid.UUID) -> Product:
        product = await self.products.get_by_id(product_id)
        if product is None:
            raise NotFoundError("Product not found", "PRODUCT_NOT_FOUND")
        return product

    async def update_product(self, product_id: uuid.UUID, data: ProductUpdate) -> Product:
        product = await self.get_product(product_id)
        updates = data.model_dump(exclude_unset=True)
        if "sku" in updates:
            await self._ensure_sku_free(updates["sku"], exclude_id=product.id)
        for field, value in updates.items():
            setattr(product, field, value)
        return await self.products.save(product)

    async def deactivate_product(self, product_id: uuid.UUID) -> Product:
        product = await self.get_product(product_id)
        product.is_active = False
        return await self.products.save(product)
