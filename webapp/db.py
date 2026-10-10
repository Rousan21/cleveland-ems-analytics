"""Database schema and connection for EMS Analytics v2."""
import os
from pathlib import Path

from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class EMSCall(Base):
    __tablename__ = "ems_calls_v2"

    object_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    priority: Mapped[str | None] = mapped_column(String(20), index=True)
    call_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    dispatch_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    scene_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Retained for future validation/geographic aggregation; NEVER send incident locations to the UI.
    block_location: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(32))


class EMSArea(Base):
    """Verified, separately reviewed OBJECTID → neighborhood lookup."""
    __tablename__ = "ems_verified_areas"

    object_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    neighborhood: Mapped[str] = mapped_column(String(100), index=True)
    source_note: Mapped[str] = mapped_column(String(250))


class SyncRun(Base):
    __tablename__ = "ems_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    record_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str | None] = mapped_column(Text)


def database_url() -> str:
    url = os.getenv("EMS_DATABASE_URL", "sqlite:///./data/ems_v2.db")
    # SQLAlchemy's default PostgreSQL driver is psycopg2, but we ship psycopg v3.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def make_engine(url: str | None = None):
    url = url or database_url()
    if url.startswith("sqlite:///") and not url.startswith("sqlite:///:memory:"):
        database_path = url.removeprefix("sqlite:///")
        if database_path and database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite:") else {}, pool_pre_ping=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine)


def init_database():
    Base.metadata.create_all(engine)
