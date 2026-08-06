from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, UniqueConstraint, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class CanonicalProfileRow(Base):
    __tablename__ = "canonical_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CanonicalProfileVersionRow(Base):
    __tablename__ = "canonical_profile_version"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class JobSnapshotRow(Base):
    __tablename__ = "job_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_url: Mapped[str] = mapped_column(nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    company: Mapped[str] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(nullable=False)
    location: Mapped[str] = mapped_column(nullable=False)
    description_text: Mapped[str] = mapped_column(nullable=False)
    detected_requirements: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_platform: Mapped[str] = mapped_column(nullable=False)
    ats_posting_id: Mapped[str | None] = mapped_column(nullable=True)
    canonical_url: Mapped[str] = mapped_column(nullable=False)
    raw_posting: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class DiscoveryLinkRow(Base):
    __tablename__ = "discovery_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(nullable=False)
    source_platform: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False)
    resolved_url: Mapped[str | None] = mapped_column(nullable=True)
    snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_snapshot.id"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApplicationPacketRow(Base):
    __tablename__ = "application_packet"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("job_snapshot.id"), nullable=False)
    profile_version: Mapped[int] = mapped_column(
        ForeignKey("canonical_profile_version.version"),
        nullable=False,
    )
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generation_key: Mapped[str] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApplicationWorkflowRow(Base):
    __tablename__ = "application_workflow"

    opportunity_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage: Mapped[str] = mapped_column(nullable=False)
    disposition: Mapped[str | None] = mapped_column(nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(nullable=True)
    outcome: Mapped[str | None] = mapped_column(nullable=True)
    packet_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_packet.id"), nullable=True
    )
    opportunity_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApplicationWorkflowTransitionRow(Base):
    __tablename__ = "application_workflow_transition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("application_workflow.opportunity_id"), nullable=False
    )
    from_stage: Mapped[str | None] = mapped_column(nullable=True)
    to_stage: Mapped[str] = mapped_column(nullable=False)
    note: Mapped[str | None] = mapped_column(nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentExportRow(Base):
    __tablename__ = "document_export"
    __table_args__ = (
        UniqueConstraint("packet_id", "document_type", "version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    packet_id: Mapped[int] = mapped_column(ForeignKey("application_packet.id"), nullable=False)
    document_type: Mapped[str] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    markdown_path: Mapped[str] = mapped_column(nullable=False)
    pdf_path: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def create_database_engine(database_url: str) -> Engine:
    parsed_url = make_url(database_url)
    database_path = parsed_url.database
    if parsed_url.drivername == "sqlite" and database_path not in (None, "", ":memory:"):
        assert database_path is not None
        Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
