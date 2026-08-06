from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import date

from pydantic import BaseModel, ConfigDict

from jobinator.application.workflow import ApplicationWorkflowModule, WorkflowItem


class AnalyticsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DailyApplications(AnalyticsModel):
    date: date
    count: int


class Rate(AnalyticsModel):
    numerator: int
    denominator: int
    rate: float | None


class GroupRate(AnalyticsModel):
    group: str
    applications: int
    responses: int
    response_rate: float


class SourceQuality(AnalyticsModel):
    source_platform: str
    applications: int
    responses: int
    recruiter_screens: int
    interviews: int
    rejections: int
    offers: int


class ScoreBucket(AnalyticsModel):
    label: str
    minimum: int
    maximum: int
    count: int


class RejectReason(AnalyticsModel):
    reason: str
    count: int


class AnalyticsDefinitions(AnalyticsModel):
    review_rejection_rate: str
    source_quality: str
    response_rate: str


class ApplicationAnalytics(AnalyticsModel):
    packets_prepared: int
    applications_submitted: int
    applications_per_day: list[DailyApplications]
    review_rejection_rate: Rate
    source_quality: list[SourceQuality]
    score_distribution: list[ScoreBucket]
    response_rate_by_role: list[GroupRate]
    response_rate_by_source: list[GroupRate]
    response_rate_by_company_type: list[GroupRate]
    common_reject_reasons: list[RejectReason]
    definitions: AnalyticsDefinitions


_BUCKETS = (("0–59", 0, 59), ("60–69", 60, 69), ("70–79", 70, 79),
            ("80–89", 80, 89), ("90–100", 90, 100))


class ApplicationAnalyticsModule:
    def __init__(self, workflow: ApplicationWorkflowModule) -> None:
        self._workflow = workflow

    def report(self) -> ApplicationAnalytics:
        items = self._workflow.board().items
        submitted = [item for item in items if item.applied_at is not None]
        review_rejections = [item for item in items if item.disposition == "skipped"]
        reviewed_decisions = [*submitted, *review_rejections]
        daily_counts = Counter(item.applied_at.date() for item in submitted if item.applied_at)
        rejection_reasons = Counter(
            event.note
            for item in items
            for event in item.outcomes
            if event.outcome_type == "rejection"
        )
        return ApplicationAnalytics(
            packets_prepared=self._workflow.prepared_packet_count(),
            applications_submitted=len(submitted),
            applications_per_day=[
                DailyApplications(date=day, count=count)
                for day, count in sorted(daily_counts.items())
            ],
            review_rejection_rate=_rate(len(review_rejections), len(reviewed_decisions)),
            source_quality=_source_quality(submitted),
            score_distribution=[
                ScoreBucket(
                    label=label,
                    minimum=minimum,
                    maximum=maximum,
                    count=sum(
                        item.original_score is not None
                        and minimum <= item.original_score.total <= maximum
                        for item in submitted
                    ),
                )
                for label, minimum, maximum in _BUCKETS
            ],
            response_rate_by_role=_group_rates(
                submitted, lambda item: item.opportunity.title
            ),
            response_rate_by_source=_group_rates(
                submitted, lambda item: item.source_platform
            ),
            response_rate_by_company_type=_group_rates(
                submitted, lambda item: item.company_type or "unspecified"
            ),
            common_reject_reasons=[
                RejectReason(reason=reason, count=count)
                for reason, count in sorted(
                    rejection_reasons.items(), key=lambda entry: (-entry[1], entry[0])
                )
            ],
            definitions=AnalyticsDefinitions(
                review_rejection_rate=(
                    "User-skipped opportunities divided by submitted applications plus "
                    "user-skipped opportunities."
                ),
                source_quality="Recorded employer outcomes by submitted application source.",
                response_rate=(
                    "Submitted applications with a recorded employer outcome divided by submitted "
                    "applications in the group."
                ),
            ),
        )


def _rate(numerator: int, denominator: int) -> Rate:
    return Rate(
        numerator=numerator,
        denominator=denominator,
        rate=numerator / denominator if denominator else None,
    )


def _group_rates(
    items: list[WorkflowItem],
    group_for: Callable[[WorkflowItem], str],
) -> list[GroupRate]:
    groups: dict[str, list[WorkflowItem]] = defaultdict(list)
    for item in items:
        groups[group_for(item)].append(item)
    rates = []
    for group, group_items in sorted(groups.items()):
        response_count = sum(bool(item.outcomes) for item in group_items)
        rates.append(GroupRate(
            group=group,
            applications=len(group_items),
            responses=response_count,
            response_rate=response_count / len(group_items),
        ))
    return rates


def _source_quality(items: list[WorkflowItem]) -> list[SourceQuality]:
    groups: dict[str, list[WorkflowItem]] = defaultdict(list)
    for item in items:
        groups[item.source_platform].append(item)
    return [
        SourceQuality(
            source_platform=source,
            applications=len(group_items),
            responses=_applications_with(group_items, "response"),
            recruiter_screens=_applications_with(group_items, "recruiter_screen"),
            interviews=_applications_with(group_items, "interview"),
            rejections=_applications_with(group_items, "rejection"),
            offers=_applications_with(group_items, "offer"),
        )
        for source, group_items in sorted(groups.items())
    ]


def _applications_with(items: list[WorkflowItem], outcome_type: str) -> int:
    return sum(
        any(event.outcome_type == outcome_type for event in item.outcomes) for item in items
    )
