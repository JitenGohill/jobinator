from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from jobinator.application.facts import FactCatalog
from jobinator.application.matching import match_profile
from jobinator.application.workflow import ApplicationWorkflowModule, WorkflowItem
from jobinator.database import StrategyProposalRow
from jobinator.discovery.models import OpportunityScore
from jobinator.discovery.module import DiscoveryModule
from jobinator.profile.module import ProfileModule

ProposalStatus = Literal["pending", "accepted", "rejected"]
ProposalDecision = Literal["accepted", "rejected"]
RankingDimension = Literal[
    "eligibility",
    "role_fit",
    "skill_overlap",
    "company_quality",
    "application_effort",
]
ProposalDirection = Literal["increase", "decrease"]

_DIMENSIONS: tuple[RankingDimension, ...] = (
    "eligibility",
    "role_fit",
    "skill_overlap",
    "company_quality",
    "application_effort",
)
_POSITIVE_OUTCOMES = ("offer", "interview", "recruiter_screen", "response")


class StrategyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GapOpportunityContext(StrategyModel):
    opportunity_id: int
    company: str
    title: str
    score: float
    source_platform: str
    matched_skills: list[str]
    matched_projects: list[str]
    matched_work_experience: list[str]


class GapFinding(StrategyModel):
    requirement: str
    occurrences: int
    priority_options: list[Literal["learning", "portfolio", "profile_presentation"]]
    opportunities: list[GapOpportunityContext]


class ProposalEvidence(StrategyModel):
    opportunity_id: int
    company: str
    title: str
    outcome: str
    dimension_value: float


class RankingProposal(StrategyModel):
    id: int
    status: ProposalStatus
    dimension: RankingDimension
    direction: ProposalDirection
    rationale: str
    current_weights: dict[str, float]
    proposed_weights: dict[str, float]
    evidence: list[ProposalEvidence]


class StrategyAdvice(StrategyModel):
    gap_findings: list[GapFinding]
    ranking_proposals: list[RankingProposal]


class ProposalDecisionRequest(StrategyModel):
    decision: ProposalDecision


class StrategyProposalNotFoundError(Exception):
    pass


class StrategyAdviceModule:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        discovery: DiscoveryModule,
        profile: ProfileModule,
        workflow: ApplicationWorkflowModule,
    ) -> None:
        self._sessions = sessions
        self._discovery = discovery
        self._profile = profile
        self._workflow = workflow

    def report(self) -> StrategyAdvice:
        board = self._workflow.board()
        proposal = self._propose_ranking_adjustment(board.items)
        if proposal is not None:
            self._record_proposal(proposal)
        with self._sessions() as session:
            rows = session.scalars(
                select(StrategyProposalRow).order_by(StrategyProposalRow.id)
            ).all()
            proposals = [self._to_proposal(row) for row in rows]
        return StrategyAdvice(
            gap_findings=self._gap_findings(board.items),
            ranking_proposals=proposals,
        )

    def decide(self, proposal_id: int, decision: ProposalDecision) -> RankingProposal:
        with self._sessions.begin() as session:
            row = session.get(StrategyProposalRow, proposal_id)
            if row is None:
                raise StrategyProposalNotFoundError
            row.status = decision
            row.decided_at = datetime.now(timezone.utc)
            session.flush()
            return self._to_proposal(row)

    def _gap_findings(self, workflow_items: list[WorkflowItem]) -> list[GapFinding]:
        profile = self._profile.get_profile().profile
        queue = self._discovery.build_daily_queue(minimum_score=0, include_maybe=True)
        scored = {
            opportunity.id: opportunity
            for opportunity in [*queue.candidates, *queue.not_queued]
            if opportunity.id is not None
        }
        dispositions = {item.opportunity_id: item.disposition for item in workflow_items}
        contexts: dict[str, list[GapOpportunityContext]] = defaultdict(list)
        labels: dict[str, str] = {}
        for opportunity in sorted(scored.values(), key=lambda item: item.id or 0):
            if (
                opportunity.score.total < 80
                or opportunity.screening.lane == "maybe"
                or dispositions.get(cast(int, opportunity.id)) is not None
            ):
                continue
            matched, missing = match_profile(
                profile,
                opportunity,
                FactCatalog.build(profile, opportunity),
            )
            context = GapOpportunityContext(
                opportunity_id=cast(int, opportunity.id),
                company=opportunity.company,
                title=opportunity.title,
                score=opportunity.score.total,
                source_platform=opportunity.source_platform,
                matched_skills=matched.skills,
                matched_projects=matched.projects,
                matched_work_experience=matched.work_experience,
            )
            for requirement in missing:
                key = " ".join(requirement.casefold().split())
                labels.setdefault(key, requirement)
                contexts[key].append(context)
        return [
            GapFinding(
                requirement=labels[key],
                occurrences=len(opportunities),
                priority_options=["learning", "portfolio", "profile_presentation"],
                opportunities=opportunities,
            )
            for key, opportunities in sorted(
                contexts.items(), key=lambda entry: (-len(entry[1]), entry[0])
            )
            if len(opportunities) >= 2
        ]

    def _propose_ranking_adjustment(
        self,
        items: list[WorkflowItem],
    ) -> tuple[str, dict[str, object]] | None:
        classified = [
            classified_item
            for item in items
            if (classified_item := _classify_outcome(item)) is not None
        ]
        positives = [entry for entry in classified if entry[1] != "rejection"]
        negatives = [entry for entry in classified if entry[1] == "rejection"]
        if not positives or not negatives:
            return None

        differences = {
            dimension: (
                _average_dimension(positives, dimension)
                - _average_dimension(negatives, dimension)
            )
            for dimension in _DIMENSIONS
        }
        dimension = max(_DIMENSIONS, key=lambda name: abs(differences[name]))
        difference = differences[dimension]
        if abs(difference) < 10:
            return None
        direction: ProposalDirection = "increase" if difference > 0 else "decrease"
        current_weights = self._discovery.current_ranking_weights()
        proposed_weights = _adjust_weights(current_weights, dimension, direction)
        evidence = [
            ProposalEvidence(
                opportunity_id=item.opportunity_id,
                company=item.opportunity.company,
                title=item.opportunity.title,
                outcome=outcome,
                dimension_value=getattr(
                    cast(OpportunityScore, item.original_score), dimension
                ).value,
            )
            for item, outcome in sorted(classified, key=lambda entry: entry[0].opportunity_id)
        ]
        positive_labels = [
            outcome
            for outcome in _POSITIVE_OUTCOMES
            if any(entry[1] == outcome for entry in positives)
        ]
        weight_changes = "; ".join(
            f"{name.replace('_', ' ')} from {current_weights[name] * 100:.0f}% "
            f"to {proposed_weights[name] * 100:.0f}%"
            for name in current_weights
            if current_weights[name] != proposed_weights[name]
        )
        rationale = (
            f"Recorded {_human_list(positive_labels)} outcomes averaged "
            f"{_average_dimension(positives, dimension):.1f} for {dimension.replace('_', ' ')}, "
            f"while rejection outcomes averaged {_average_dimension(negatives, dimension):.1f}. "
            f"Proposed weights: {weight_changes}. No ranking changes until accepted."
        )
        return (
            f"ranking:{dimension}:{direction}",
            {
                "dimension": dimension,
                "direction": direction,
                "rationale": rationale,
                "current_weights": current_weights,
                "proposed_weights": proposed_weights,
                "evidence": [entry.model_dump(mode="json") for entry in evidence],
            },
        )

    def _record_proposal(self, proposal: tuple[str, dict[str, object]]) -> None:
        semantic_key, payload = proposal
        with self._sessions.begin() as session:
            row = session.scalar(
                select(StrategyProposalRow).where(
                    StrategyProposalRow.semantic_key == semantic_key
                )
            )
            if row is None:
                session.add(
                    StrategyProposalRow(
                        semantic_key=semantic_key,
                        status="pending",
                        payload=payload,
                        created_at=datetime.now(timezone.utc),
                        decided_at=None,
                    )
                )
            elif row.status == "pending":
                row.payload = payload

    @staticmethod
    def _to_proposal(row: StrategyProposalRow) -> RankingProposal:
        return RankingProposal(id=row.id, status=cast(ProposalStatus, row.status), **row.payload)


def _classify_outcome(item: WorkflowItem) -> tuple[WorkflowItem, str] | None:
    if item.original_score is None or item.applied_at is None:
        return None
    if not item.outcomes:
        return None
    latest = max(item.outcomes, key=lambda event: event.occurred_at)
    return item, latest.outcome_type


def _average_dimension(
    entries: list[tuple[WorkflowItem, str]],
    dimension: RankingDimension,
) -> float:
    values = [
        getattr(cast(OpportunityScore, item.original_score), dimension).value
        for item, _ in entries
    ]
    return sum(values) / len(values)


def _adjust_weights(
    current: dict[str, float],
    dimension: RankingDimension,
    direction: ProposalDirection,
) -> dict[str, float]:
    adjusted = dict(current)
    other = max((name for name in adjusted if name != dimension), key=adjusted.__getitem__)
    delta = min(0.05, adjusted[other] if direction == "increase" else adjusted[dimension])
    if direction == "increase":
        adjusted[dimension] += delta
        adjusted[other] -= delta
    else:
        adjusted[dimension] -= delta
        adjusted[other] += delta
    return {name: round(value, 4) for name, value in adjusted.items()}


def _human_list(values: list[str]) -> str:
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"
