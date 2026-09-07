from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Inspection(Base):
    __tablename__ = "inspections"
    __table_args__ = (
        Index("ix_inspections_queue", "status", "available_at", "lease_until"),
        Index("ix_inspections_owner_created", "owner_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(128))
    image_key: Mapped[str] = mapped_column(String(512))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[float] = mapped_column(Float)
    completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    available_at: Mapped[float] = mapped_column(Float)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    overall_result: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class InspectionEvent(Base):
    __tablename__ = "inspection_events"
    __table_args__ = (Index("ix_events_inspection", "inspection_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    inspection_id: Mapped[str] = mapped_column(ForeignKey("inspections.id"))
    event_type: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float)
    event_data: Mapped[dict[str, Any]] = mapped_column(JSON)


def make_engine(url: str) -> Engine:
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite":
        if parsed.database and parsed.database != ":memory:":
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
    return create_engine(url, pool_pre_ping=True)
