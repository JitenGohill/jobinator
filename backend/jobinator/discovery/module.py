from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Literal, Protocol, cast

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from jobinator.database import CanonicalProfileRow, JobSnapshotRow
from jobinator.discovery.models import (
    IngestionResult,
    JobSnapshot,
    ScreenedJob,
    SourceConfiguration,
)
from jobinator.discovery.screening import ScreeningPolicy
from jobinator.profile.models import CanonicalProfile

logger = logging.getLogger(__name__)


class SourceAdapter(Protocol):
    platform: str

    def discover(
        self,
        source: SourceConfiguration,
        fetched_at: datetime,
    ) -> Awaitable[list[JobSnapshot]]: ...


class SourceNotConfiguredError(Exception):
    pass


class DiscoveryModule:
    """Run source adapters and preserve their immutable discovery snapshots."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        sources: list[SourceConfiguration],
        adapters: dict[str, SourceAdapter],
        clock: Callable[[], datetime],
    ) -> None:
        self._sessions = sessions
        self._sources = sources
        self._adapters = adapters
        self._clock = clock

    async def ingest_configured(self) -> IngestionResult:
        if not self._sources:
            raise SourceNotConfiguredError

        snapshots: list[JobSnapshot] = []
        for source in self._sources:
            adapter = self._adapters[source.platform]
            try:
                snapshots.extend(await adapter.discover(source, self._clock()))
            except Exception as error:
                logger.warning(
                    "Discovery failed for %s source %s (%s).",
                    source.platform,
                    source.identifier,
                    type(error).__name__,
                )
                raise

        with self._sessions.begin() as session:
            for snapshot in snapshots:
                session.add(
                    JobSnapshotRow(
                        source_url=snapshot.source_url,
                        fetched_at=snapshot.fetched_at,
                        company=snapshot.company,
                        title=snapshot.title,
                        location=snapshot.location,
                        description_text=snapshot.description_text,
                        detected_requirements=snapshot.detected_requirements,
                        source_platform=snapshot.source_platform,
                        ats_posting_id=snapshot.ats_posting_id,
                        canonical_url=snapshot.canonical_url,
                        raw_posting=snapshot.raw_posting,
                    )
                )
        return IngestionResult(discovered=len(snapshots))

    def list_discovered(self) -> list[ScreenedJob]:
        with self._sessions() as session:
            rows = session.scalars(
                select(JobSnapshotRow).order_by(
                    JobSnapshotRow.fetched_at.desc(),
                    JobSnapshotRow.id.desc(),
                )
            ).all()
            profile_row = session.get(CanonicalProfileRow, 1)
            profile = (
                CanonicalProfile.model_validate(profile_row.payload)
                if profile_row is not None
                else None
            )
            policy = ScreeningPolicy(profile)
            snapshots = [self._to_snapshot(row) for row in rows]
            return [
                ScreenedJob(
                    **snapshot.model_dump(),
                    screening=policy.screen(snapshot),
                )
                for snapshot in snapshots
            ]

    @staticmethod
    def _to_snapshot(row: JobSnapshotRow) -> JobSnapshot:
        fetched_at = row.fetched_at
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        return JobSnapshot(
            id=row.id,
            source_url=row.source_url,
            fetched_at=fetched_at,
            company=row.company,
            title=row.title,
            location=row.location,
            description_text=row.description_text,
            detected_requirements=row.detected_requirements,
            source_platform=cast(Literal["greenhouse"], row.source_platform),
            ats_posting_id=row.ats_posting_id,
            canonical_url=row.canonical_url,
            raw_posting=row.raw_posting,
        )
