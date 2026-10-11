"""Settings > Import & export: moving in from spreadsheets or another
system, and taking everything out again. Admins and managers only."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.core.database import CommitBeforeResponseRoute
from app.models.enums import UserRole
from app.models.user import User
from app.services.data_service import EXPORTS, FIELDS, MAX_ROWS, ImportService, export_csv

router = APIRouter(route_class=CommitBeforeResponseRoute, tags=["import and export"])
_managers = require_role(UserRole.ADMIN, UserRole.MANAGER)


class ImportIn(BaseModel):
    rows: list[dict[str, str | int | float | None]] = Field(max_length=MAX_ROWS)
    update_existing: bool = False


@router.get("/imports/fields")
async def import_fields(_: User = Depends(_managers)):
    return {"fields": FIELDS, "max_rows": MAX_ROWS}


@router.post("/imports/{entity}")
async def run_import(entity: Literal["customers", "products", "deals"], data: ImportIn, db: AsyncSession = Depends(get_db), user: User = Depends(_managers)):
    return await ImportService(db, user).run(entity, data.rows, data.update_existing)


@router.get("/exports/{entity}")
async def run_export(entity: Literal[EXPORTS], db: AsyncSession = Depends(get_db), _: User = Depends(_managers)):  # type: ignore[valid-type]
    body = await export_csv(db, entity)
    filename = f"ygt-{entity}-{date.today().isoformat()}.csv"
    return Response(content=body, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
