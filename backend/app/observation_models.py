from __future__ import annotations

from enum import Enum
from math import isfinite
import re

from pydantic import BaseModel, Field, field_validator


class ObservationCategory(str, Enum):
    curb_ramp_present = "curb_ramp_present"
    curb_ramp_appears_absent = "curb_ramp_appears_absent"
    stairs = "stairs"
    sidewalk_obstruction = "sidewalk_obstruction"
    uneven_surface = "uneven_surface"
    sidewalk_condition_issue = "sidewalk_condition_issue"
    crossing_issue = "crossing_issue"
    other = "other"


class ObservationCreate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    category: ObservationCategory
    description: str | None = Field(default=None, max_length=500)

    @field_validator("latitude", "longitude")
    @classmethod
    def finite_coordinates(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("Coordinates must be finite numbers")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if any(ord(char) < 32 and char not in "\t\n\r" for char in normalized):
            raise ValueError("Description contains unsupported control characters")
        normalized = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email removed]", normalized)
        normalized = re.sub(r"(?<!\w)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\w)", "[phone removed]", normalized)
        return normalized or None
