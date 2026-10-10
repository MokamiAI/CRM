import re
import uuid
from datetime import date
from typing import Any

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.models.custom_field import CustomFieldDefinition
from app.schemas.custom_field import CustomFieldCreate, CustomFieldUpdate


class CustomFieldError(AppError):
    def __init__(self, message: str):
        super().__init__(message, "CUSTOM_FIELD_INVALID", status.HTTP_422_UNPROCESSABLE_ENTITY)


def _slug(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return (slug or "field")[:48]


class CustomFieldService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_fields(self, entity: str | None = None) -> list[CustomFieldDefinition]:
        query = select(CustomFieldDefinition).order_by(
            CustomFieldDefinition.entity, CustomFieldDefinition.position, CustomFieldDefinition.created_at
        )
        if entity:
            query = query.where(CustomFieldDefinition.entity == entity)
        return list((await self.db.scalars(query)).all())

    async def get_field(self, field_id: uuid.UUID) -> CustomFieldDefinition:
        field = await self.db.get(CustomFieldDefinition, field_id)
        if field is None:
            raise NotFoundError("Custom field not found", "CUSTOM_FIELD_NOT_FOUND")
        return field

    async def create_field(self, data: CustomFieldCreate) -> CustomFieldDefinition:
        if data.field_type == "select" and not data.options:
            raise CustomFieldError("A dropdown field needs at least one option")
        existing = {f.key for f in await self.list_fields(data.entity)}
        base = key = _slug(data.label)
        n = 2
        while key in existing:
            key, n = f"{base}_{n}", n + 1
        position = await self.db.scalar(
            select(func.coalesce(func.max(CustomFieldDefinition.position) + 1, 0)).where(
                CustomFieldDefinition.entity == data.entity
            )
        )
        field = CustomFieldDefinition(
            entity=data.entity,
            key=key,
            label=data.label.strip(),
            field_type=data.field_type,
            options=data.options if data.field_type == "select" else [],
            required=data.required,
            position=position,
        )
        self.db.add(field)
        await self.db.flush()
        return field

    async def update_field(self, field_id: uuid.UUID, data: CustomFieldUpdate) -> CustomFieldDefinition:
        field = await self.get_field(field_id)
        changes = data.model_dump(exclude_unset=True)
        if "options" in changes:
            if field.field_type != "select":
                changes.pop("options")
            elif not changes["options"]:
                raise CustomFieldError("A dropdown field needs at least one option")
        for name, value in changes.items():
            setattr(field, name, value.strip() if name == "label" else value)
        await self.db.flush()
        return field

    async def delete_field(self, field_id: uuid.UUID) -> None:
        # Stored values stay in the records' JSON but are no longer shown.
        await self.db.delete(await self.get_field(field_id))
        await self.db.flush()

    async def clean_values(
        self, entity: str, values: dict[str, Any], current: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Validate submitted values against the definitions and return the
        merged result to store. Blank values clear a field; unknown keys are
        rejected. `current` is the record's existing values on update."""
        fields = {f.key: f for f in await self.list_fields(entity)}
        merged = dict(current or {})
        for key, raw in values.items():
            field = fields.get(key)
            if field is None:
                raise CustomFieldError(f"Unknown custom field: {key}")
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                merged.pop(key, None)
                continue
            merged[key] = self._coerce(field, raw)
        missing = [f.label for f in fields.values() if f.required and merged.get(f.key) in (None, "")]
        if missing:
            raise CustomFieldError(f"Required: {', '.join(missing)}")
        return merged

    @staticmethod
    def _coerce(field: CustomFieldDefinition, raw: Any) -> Any:
        try:
            if field.field_type == "text":
                return str(raw).strip()[:1000]
            if field.field_type == "number":
                if isinstance(raw, bool):
                    raise ValueError
                number = float(str(raw).replace(",", ".").replace(" ", ""))
                return int(number) if number.is_integer() else number
            if field.field_type == "date":
                return date.fromisoformat(str(raw)).isoformat()
            if field.field_type == "boolean":
                if isinstance(raw, bool):
                    return raw
                if str(raw).lower() in ("true", "1", "yes"):
                    return True
                if str(raw).lower() in ("false", "0", "no"):
                    return False
                raise ValueError
            if field.field_type == "select":
                if str(raw) not in field.options:
                    raise ValueError
                return str(raw)
        except ValueError:
            pass
        raise CustomFieldError(f"Invalid value for {field.label}")
