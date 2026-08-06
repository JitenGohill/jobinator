from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from jobinator.application.models import ApplicationPacket
from jobinator.database import (
    ApplicationPacketRow,
    ApplicationWorkflowRow,
    ApplicationWorkflowTransitionRow,
    DocumentExportRow,
)
from jobinator.discovery.models import OpportunityScore
from jobinator.discovery.module import DiscoveryModule
from jobinator.discovery.queue import CanonicalProfileRequiredError

WorkflowStage = Literal[
    "discovered",
    "shortlisted",
    "packet_ready",
    "reviewed",
    "applied",
    "rejected_skipped",
    "follow_up",
    "outcome",
]
WorkflowDisposition = Literal["rejected", "skipped"]
OutcomeType = Literal["response", "recruiter_screen", "interview", "rejection", "offer"]
CompanyType = Literal[
    "product",
    "startup",
    "enterprise",
    "agency",
    "consultancy",
    "nonprofit",
    "government",
    "other",
]


class WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkflowTransition(WorkflowModel):
    from_stage: WorkflowStage | None
    to_stage: WorkflowStage
    note: str | None
    occurred_at: datetime


class WorkflowOpportunity(WorkflowModel):
    company: str
    title: str
    location: str
    direct_apply_link: str


class SubmittedDocumentVersion(WorkflowModel):
    document_type: Literal["cv", "cover_letter"]
    version: int = Field(ge=1)


class OutcomeEvent(WorkflowModel):
    outcome_type: OutcomeType
    note: str
    occurred_at: datetime


class WorkflowItem(WorkflowModel):
    opportunity_id: int
    stage: WorkflowStage
    disposition: WorkflowDisposition | None
    skip_reason: str | None
    outcome: str | None
    source_platform: str
    original_score: OpportunityScore | None
    packet_id: int | None
    applied_at: datetime | None
    company_type: CompanyType | None
    document_versions: list[SubmittedDocumentVersion]
    outcomes: list[OutcomeEvent]
    opportunity: WorkflowOpportunity
    packet: ApplicationPacket | None
    history: list[WorkflowTransition]


class WorkflowBoard(WorkflowModel):
    items: list[WorkflowItem]


class WorkflowTransitionRequest(WorkflowModel):
    target_stage: WorkflowStage
    skip_reason: str | None = Field(default=None, min_length=1)
    submitted_externally: bool = False
    outcome: str | None = Field(default=None, min_length=1)
    outcome_type: OutcomeType | None = None
    occurred_at: datetime | None = None
    company_type: CompanyType | None = None
    document_versions: list[SubmittedDocumentVersion] = Field(default_factory=list)


class WorkflowItemNotFoundError(Exception):
    pass


class InvalidWorkflowTransitionError(Exception):
    pass


class ExternalSubmissionConfirmationRequiredError(Exception):
    pass


class WorkflowDetailRequiredError(Exception):
    pass


class SubmittedDocumentVersionNotFoundError(Exception):
    pass


_ALLOWED_TRANSITIONS: dict[WorkflowStage, set[WorkflowStage]] = {
    "discovered": {"shortlisted", "rejected_skipped"},
    "shortlisted": {"rejected_skipped"},
    "packet_ready": {"reviewed", "rejected_skipped"},
    "reviewed": {"applied", "rejected_skipped"},
    "applied": {"follow_up", "outcome"},
    "follow_up": {"outcome"},
    "rejected_skipped": set(),
    "outcome": {"outcome"},
}


class ApplicationWorkflowModule:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        discovery_module: DiscoveryModule,
    ) -> None:
        self._sessions = sessions
        self._discovery_module = discovery_module

    def board(self) -> WorkflowBoard:
        self._seed_discovered_opportunities()
        with self._sessions() as session:
            rows = session.scalars(
                select(ApplicationWorkflowRow).order_by(
                    ApplicationWorkflowRow.updated_at.desc(),
                    ApplicationWorkflowRow.opportunity_id,
                )
            ).all()
            return WorkflowBoard(items=[self._item(session, row) for row in rows])

    def record_packet(self, packet: ApplicationPacket) -> None:
        self._seed_discovered_opportunities()
        with self._sessions.begin() as session:
            row = session.get(ApplicationWorkflowRow, packet.opportunity_id)
            if row is None:
                raise WorkflowItemNotFoundError
            row.packet_id = packet.id
            details = dict(row.opportunity_payload)
            if details.get("original_score") is None:
                details["original_score"] = packet.score.model_dump(mode="json")
            row.opportunity_payload = details
            if row.stage == "shortlisted":
                self._move(session, row, "packet_ready", "Review packet prepared.")

    def transition(
        self,
        opportunity_id: int,
        request: WorkflowTransitionRequest,
    ) -> WorkflowItem:
        self._seed_discovered_opportunities()
        with self._sessions.begin() as session:
            row = session.get(ApplicationWorkflowRow, opportunity_id)
            if row is None:
                raise WorkflowItemNotFoundError
            current_stage = cast(WorkflowStage, row.stage)
            if request.target_stage not in _ALLOWED_TRANSITIONS[current_stage]:
                raise InvalidWorkflowTransitionError
            if request.target_stage == "applied" and not request.submitted_externally:
                raise ExternalSubmissionConfirmationRequiredError
            if request.target_stage == "rejected_skipped" and not request.skip_reason:
                raise WorkflowDetailRequiredError
            if request.target_stage == "outcome" and not request.outcome:
                raise WorkflowDetailRequiredError

            occurred_at = request.occurred_at or datetime.now(timezone.utc)
            details = dict(row.opportunity_payload)

            note = None
            if request.target_stage == "applied":
                self._validate_document_versions(session, row, request.document_versions)
                note = "Submitted externally by the user."
                details.update(
                    {
                        "applied_at": occurred_at.isoformat(),
                        "company_type": request.company_type,
                        "document_versions": [
                            version.model_dump(mode="json")
                            for version in request.document_versions
                        ],
                    }
                )
            elif request.target_stage == "rejected_skipped":
                row.disposition = "skipped"
                row.skip_reason = request.skip_reason
                note = request.skip_reason
            elif request.target_stage == "outcome":
                row.outcome = request.outcome
                note = request.outcome
                if request.outcome_type is not None:
                    outcomes = list(details.get("outcomes", []))
                    outcomes.append(
                        {
                            "outcome_type": request.outcome_type,
                            "note": request.outcome,
                            "occurred_at": occurred_at.isoformat(),
                        }
                    )
                    details["outcomes"] = outcomes
            row.opportunity_payload = details
            self._move(session, row, request.target_stage, note, occurred_at)
            session.flush()
            return self._item(session, row)

    def _seed_discovered_opportunities(self) -> None:
        opportunities = self._discovery_module.list_discovered()
        try:
            queue = self._discovery_module.build_daily_queue(
                minimum_score=60,
                include_maybe=False,
            )
            shortlisted_ids = {candidate.id for candidate in queue.candidates}
            scores = {
                candidate.id: candidate.score.model_dump(mode="json")
                for candidate in [*queue.candidates, *queue.not_queued]
            }
        except CanonicalProfileRequiredError:
            shortlisted_ids = set()
            scores = {}
        now = datetime.now(timezone.utc)
        with self._sessions.begin() as session:
            for opportunity in opportunities:
                if opportunity.id is None:
                    continue
                if session.get(ApplicationWorkflowRow, opportunity.id) is not None:
                    continue
                if opportunity.screening.lane == "rejected":
                    stage: WorkflowStage = "rejected_skipped"
                    disposition: WorkflowDisposition | None = "rejected"
                    note = "; ".join(opportunity.screening.reasons)
                elif opportunity.id in shortlisted_ids:
                    stage = "shortlisted"
                    disposition = None
                    note = "Added to the quality-first shortlist."
                else:
                    stage = "discovered"
                    disposition = None
                    note = "Discovered for review."
                row = ApplicationWorkflowRow(
                    opportunity_id=opportunity.id,
                    stage=stage,
                    disposition=disposition,
                    skip_reason=None,
                    outcome=None,
                    packet_id=None,
                    opportunity_payload={
                        "company": opportunity.company,
                        "title": opportunity.title,
                        "location": opportunity.location,
                        "direct_apply_link": opportunity.preferred_apply_url,
                        "source_platform": opportunity.source_platform,
                        "original_score": scores.get(opportunity.id),
                        "applied_at": None,
                        "company_type": None,
                        "document_versions": [],
                        "outcomes": [],
                    },
                    updated_at=now,
                )
                session.add(row)
                session.add(
                    ApplicationWorkflowTransitionRow(
                        opportunity_id=opportunity.id,
                        from_stage=None,
                        to_stage=stage,
                        note=note,
                        occurred_at=now,
                    )
                )

    @staticmethod
    def _move(
        session: Session,
        row: ApplicationWorkflowRow,
        target_stage: WorkflowStage,
        note: str | None,
        occurred_at: datetime | None = None,
    ) -> None:
        previous = row.stage
        occurred_at = occurred_at or datetime.now(timezone.utc)
        row.stage = target_stage
        row.updated_at = occurred_at
        session.add(
            ApplicationWorkflowTransitionRow(
                opportunity_id=row.opportunity_id,
                from_stage=previous,
                to_stage=target_stage,
                note=note,
                occurred_at=occurred_at,
            )
        )

    @staticmethod
    def _validate_document_versions(
        session: Session,
        row: ApplicationWorkflowRow,
        versions: list[SubmittedDocumentVersion],
    ) -> None:
        if not versions:
            return
        if row.packet_id is None:
            raise SubmittedDocumentVersionNotFoundError
        available = {
            (document.document_type, document.version)
            for document in session.scalars(
                select(DocumentExportRow).where(DocumentExportRow.packet_id == row.packet_id)
            ).all()
        }
        if any((version.document_type, version.version) not in available for version in versions):
            raise SubmittedDocumentVersionNotFoundError

    @staticmethod
    def _item(session: Session, row: ApplicationWorkflowRow) -> WorkflowItem:
        details = row.opportunity_payload
        transitions = session.scalars(
            select(ApplicationWorkflowTransitionRow)
            .where(ApplicationWorkflowTransitionRow.opportunity_id == row.opportunity_id)
            .order_by(ApplicationWorkflowTransitionRow.id)
        ).all()
        packet_row = (
            session.get(ApplicationPacketRow, row.packet_id)
            if row.packet_id is not None
            else None
        )
        packet = (
            ApplicationPacket(
                id=packet_row.id,
                profile_version=packet_row.profile_version,
                **packet_row.payload,
            )
            if packet_row is not None
            else None
        )
        return WorkflowItem(
            opportunity_id=row.opportunity_id,
            stage=cast(WorkflowStage, row.stage),
            disposition=cast(WorkflowDisposition | None, row.disposition),
            skip_reason=row.skip_reason,
            outcome=row.outcome,
            source_platform=str(details.get("source_platform", "unknown")),
            original_score=OpportunityScore.model_validate(details["original_score"])
            if details.get("original_score") is not None
            else None,
            packet_id=row.packet_id,
            applied_at=details.get("applied_at"),
            company_type=cast(CompanyType | None, details.get("company_type")),
            document_versions=[
                SubmittedDocumentVersion.model_validate(version)
                for version in details.get("document_versions", [])
            ],
            outcomes=[
                OutcomeEvent.model_validate(event) for event in details.get("outcomes", [])
            ],
            opportunity=WorkflowOpportunity(
                company=str(details["company"]),
                title=str(details["title"]),
                location=str(details["location"]),
                direct_apply_link=str(details["direct_apply_link"]),
            ),
            packet=packet,
            history=[
                WorkflowTransition(
                    from_stage=cast(WorkflowStage | None, transition.from_stage),
                    to_stage=cast(WorkflowStage, transition.to_stage),
                    note=transition.note,
                    occurred_at=transition.occurred_at,
                )
                for transition in transitions
            ],
        )
