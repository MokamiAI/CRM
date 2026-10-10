import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.custom_field import CUSTOM_FIELD_ENTITIES, CUSTOM_FIELD_TYPES

Entity = Literal[CUSTOM_FIELD_ENTITIES]
FieldType = Literal[CUSTOM_FIELD_TYPES]


def _clean_options(value: list[str] | None) -> list[str] | None:
    if value is None:
        return value
    seen: list[str] = []
    for option in (o.strip() for o in value):
        if option and option not in seen:
            seen.append(option[:100])
    return seen


class CustomFieldCreate(BaseModel):
    entity: Entity
    label: str = Field(min_length=1, max_length=100)
    field_type: FieldType
    options: list[str] = Field(default_factory=list, max_length=50)
    required: bool = False

    _options = field_validator("options")(classmethod(lambda cls, v: _clean_options(v)))


class CustomFieldUpdate(BaseModel):
    # The type is fixed once created so existing values stay valid.
    label: str | None = Field(default=None, min_length=1, max_length=100)
    options: list[str] | None = Field(default=None, max_length=50)
    required: bool | None = None
    position: int | None = Field(default=None, ge=0)

    _options = field_validator("options")(classmethod(lambda cls, v: _clean_options(v)))


class CustomFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity: str
    key: str
    label: str
    field_type: str
    options: list[str]
    required: bool
    position: int
