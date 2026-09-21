from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Status(StrEnum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DefectType(StrEnum):
    SHORT = "short"
    SPUR = "spur"
    SPURIOUS_COPPER = "spurious_copper"
    OPEN = "open"
    MOUSE_BITE = "mouse_bite"
    HOLE_BREAKOUT = "hole_breakout"
    CONDUCTOR_SCRATCH = "conductor_scratch"
    CONDUCTOR_FOREIGN_OBJECT = "conductor_foreign_object"
    BASE_MATERIAL_FOREIGN_OBJECT = "base_material_foreign_object"
    MISSING_COMPONENT = "missing_component"
    MISALIGNED_COMPONENT = "misaligned_component"
    SOLDER_BRIDGE = "solder_bridge"
    DAMAGED_COMPONENT = "damaged_component"
    BOARD_DAMAGE = "board_damage"
    FOREIGN_OBJECT = "foreign_object"
    CONTAMINATION = "contamination"


class BoundingBox(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, frozen=True)
    x1: float = Field(ge=0)
    y1: float = Field(ge=0)
    x2: float = Field(gt=0)
    y2: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("Bounding box must have positive width and height")
        return self


class Detection(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, frozen=True)
    defect_type: DefectType
    confidence: float = Field(ge=0, le=1)
    bbox: BoundingBox


class Finding(Detection):
    severity: Literal["critical", "high", "medium"]
    confidence_band: Literal["high", "review"]


class Report(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    inspection_id: str
    model_version: str
    is_demo: bool
    is_experimental: bool = False
    overall_result: Literal["NOT_EVALUATED", "REVIEW_REQUIRED", "NO_VISIBLE_DEFECTS_DETECTED"]
    inference_time_ms: int = Field(ge=0)
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    detections: list[Finding]
    ignored_detection_count: int = Field(ge=0)
    decision_policy_version: str = "provisional-1"
    limitations: list[str]


class InspectionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: Status
    created_at: datetime
    completed_at: datetime | None
    width: int
    height: int
    attempts: int
    model_version: str | None
    error_code: str | None
    overall_result: str | None


class Submission(BaseModel):
    inspection_id: str
    status: Literal[Status.QUEUED] = Status.QUEUED


class History(BaseModel):
    items: list[InspectionSummary]
    limit: int
    offset: int
