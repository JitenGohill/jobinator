from __future__ import annotations

import re

from jobinator.discovery.models import (
    CandidateQueue,
    ExpansionLever,
    OpportunityScore,
    QueueCriteria,
    QueueTarget,
    ScoreDimension,
    ScoredOpportunity,
    ScreenedOpportunity,
)
from jobinator.profile.models import CanonicalProfile

DEFAULT_MINIMUM_TARGET = 25
DEFAULT_MAXIMUM_TARGET = 30
DEFAULT_MINIMUM_SCORE = 60
SCORE_WEIGHTS = {
    "eligibility": 0.30,
    "role_fit": 0.25,
    "skill_overlap": 0.20,
    "company_quality": 0.15,
    "application_effort": 0.10,
}

_ATS_PLATFORMS = {"ashby", "greenhouse", "lever", "workday"}
_OFFICIAL_PLATFORMS = {"company", "official"}
_KNOWN_TECHNOLOGIES = {
    "angular": "Angular",
    "c#": "C#",
    "c++": "C++",
    "django": "Django",
    "fastapi": "FastAPI",
    "go": "Go",
    "golang": "Go",
    "java": "Java",
    "javascript": "JavaScript",
    "kotlin": "Kotlin",
    ".net": ".NET",
    "node": "Node",
    "php": "PHP",
    "python": "Python",
    "rails": "Rails",
    "react": "React",
    "ruby": "Ruby",
    "rust": "Rust",
    "scala": "Scala",
    "sqlite": "SQLite",
    "swift": "Swift",
    "typescript": "TypeScript",
    "vue": "Vue",
}
_ROLE_CATEGORIES = (
    ("backend", ("backend", "back-end", "api engineer")),
    ("full-stack", ("full-stack", "full stack")),
    ("platform", ("platform",)),
    ("internal-tools", ("internal tools", "internal-tools")),
    ("ai-adjacent", ("ai ", "machine learning")),
    ("software", ("software engineer", "software developer")),
)


class CanonicalProfileRequiredError(Exception):
    pass


def build_candidate_queue(
    opportunities: list[ScreenedOpportunity],
    profile: CanonicalProfile,
    *,
    minimum_score: int = DEFAULT_MINIMUM_SCORE,
    include_maybe: bool = False,
    minimum_target: int = DEFAULT_MINIMUM_TARGET,
    maximum_target: int = DEFAULT_MAXIMUM_TARGET,
    weights: dict[str, float] | None = None,
) -> CandidateQueue:
    if minimum_target > maximum_target:
        raise ValueError("The minimum queue target cannot exceed the maximum.")

    ranking_weights = weights or SCORE_WEIGHTS
    scored = sorted(
        (
            _score_opportunity(opportunity, profile, ranking_weights)
            for opportunity in opportunities
            if opportunity.screening.lane != "rejected"
        ),
        key=lambda opportunity: (
            -opportunity.score.total,
            opportunity.title.lower(),
            opportunity.id or 0,
        ),
    )
    qualified = [
        opportunity
        for opportunity in scored
        if opportunity.score.total >= minimum_score
        and (include_maybe or opportunity.screening.lane != "maybe")
    ]
    regular = [
        opportunity
        for opportunity in qualified
        if opportunity.screening.lane != "stretch"
    ]
    stretch = [
        opportunity
        for opportunity in qualified
        if opportunity.screening.lane == "stretch"
    ]
    stretch_limit = min(
        len(stretch),
        maximum_target // 4,
        len(regular) // 3,
    )
    selectable_ids = {
        id(opportunity) for opportunity in [*regular, *stretch[:stretch_limit]]
    }
    candidates = [
        opportunity
        for opportunity in qualified
        if id(opportunity) in selectable_ids
    ][:maximum_target]
    candidate_ids = {id(opportunity) for opportunity in candidates}
    not_queued = [
        opportunity for opportunity in scored if id(opportunity) not in candidate_ids
    ]
    shortfall = max(0, minimum_target - len(candidates))
    criteria = QueueCriteria(
        minimum_score=minimum_score,
        include_maybe=include_maybe,
    )
    return CandidateQueue(
        target=QueueTarget(minimum=minimum_target, maximum=maximum_target),
        criteria=criteria,
        candidates=candidates,
        not_queued=not_queued,
        shortfall=shortfall,
        summary=_queue_summary(
            len(candidates),
            minimum_target,
            shortfall,
            criteria,
        ),
        expansion_levers=_expansion_levers(
            scored,
            criteria,
            shortfall,
        ),
    )


def _score_opportunity(
    opportunity: ScreenedOpportunity,
    profile: CanonicalProfile,
    weights: dict[str, float],
) -> ScoredOpportunity:
    dimensions = {
        "eligibility": _eligibility_score(opportunity),
        "role_fit": _role_fit_score(opportunity, profile),
        "skill_overlap": _skill_overlap_score(opportunity, profile),
        "company_quality": _company_quality_score(opportunity),
        "application_effort": _application_effort_score(opportunity),
    }
    total = round(
        sum(
            dimensions[name].value * weight
            for name, weight in weights.items()
        ),
        2,
    )
    return ScoredOpportunity(
        **opportunity.model_dump(),
        score=OpportunityScore(
            total=total,
            weights=weights,
            **dimensions,
        ),
    )


def _eligibility_score(opportunity: ScreenedOpportunity) -> ScoreDimension:
    values = {"eligible": 100, "stretch": 75, "maybe": 50}
    lane = opportunity.screening.lane
    value = values[lane]
    labels = {
        "eligible": "Eligible",
        "stretch": "Stretch",
        "maybe": "Manual review",
    }
    evidence = "; ".join(
        reason.removesuffix(".") for reason in opportunity.screening.reasons
    )
    explanation = f"{labels[lane]} based on screening: {evidence}."
    return ScoreDimension(value=value, explanation=explanation)


def _role_fit_score(
    opportunity: ScreenedOpportunity,
    profile: CanonicalProfile,
) -> ScoreDimension:
    opportunity_role = _role_category(
        f"{opportunity.title}\n{opportunity.description_text}"
    )
    profile_text = "\n".join(
        (
            profile.base_cv,
            *(project.summary for project in profile.projects),
            *(experience.title for experience in profile.work_history),
        )
    )
    profile_role = _role_category(profile_text)
    if opportunity_role == profile_role and opportunity_role != "software":
        value = 100
        explanation = (
            f"Strong {opportunity_role} fit with the canonical profile's "
            f"{profile_role} focus."
        )
    else:
        adjacent_scores = {
            "platform": 85,
            "full-stack": 80,
            "internal-tools": 80,
            "software": 80,
            "ai-adjacent": 70,
        }
        value = adjacent_scores.get(opportunity_role, 70)
        explanation = (
            f"{opportunity_role.title()} role is adjacent to the canonical "
            f"profile's {profile_role} focus."
        )
    return ScoreDimension(value=value, explanation=explanation)


def _skill_overlap_score(
    opportunity: ScreenedOpportunity,
    profile: CanonicalProfile,
) -> ScoreDimension:
    profile_skills = {
        name.lower(): _KNOWN_TECHNOLOGIES.get(name.lower(), name)
        for name in profile.known_technologies().values()
    }
    required: set[str] = set()
    for requirement in opportunity.detected_requirements:
        recognized = _technology_names(requirement, profile_skills)
        required.update(recognized or {requirement.strip()})
    if not required:
        required = _technology_names(opportunity.description_text, profile_skills)
    known = set(profile_skills.values())
    if not required:
        return ScoreDimension(
            value=60,
            explanation="No specific technology requirements were detected to compare.",
        )
    matched = sorted(required & known)
    value = round(100 * len(matched) / len(required))
    if matched:
        explanation = (
            f"Matches {len(matched)} of {len(required)} detected technologies: "
            f"{_human_list(matched)}."
        )
    else:
        explanation = (
            f"Matches 0 of {len(required)} detected technologies in the canonical profile."
        )
    return ScoreDimension(value=value, explanation=explanation)


def _company_quality_score(opportunity: ScreenedOpportunity) -> ScoreDimension:
    platform = opportunity.source_platform.lower()
    if platform in _OFFICIAL_PLATFORMS:
        return ScoreDimension(
            value=100,
            explanation=f"Official company listing from {opportunity.company}.",
        )
    if platform in _ATS_PLATFORMS:
        return ScoreDimension(
            value=85,
            explanation=(
                f"Direct {platform.title()} ATS listing for {opportunity.company}."
            ),
        )
    return ScoreDimension(
        value=40,
        explanation=(
            f"Third-party listing for {opportunity.company}; verify the employer and route."
        ),
    )


def _application_effort_score(opportunity: ScreenedOpportunity) -> ScoreDimension:
    requirement_count = len(opportunity.detected_requirements)
    platform = opportunity.source_platform.lower()
    if platform in _OFFICIAL_PLATFORMS and requirement_count <= 2:
        value = 100
        route = "official route"
        effort = "Low"
    elif platform in _ATS_PLATFORMS and requirement_count <= 2:
        value = 90
        route = "direct ATS route"
        effort = "Low"
    elif platform in _ATS_PLATFORMS:
        value = 80
        route = "direct ATS route"
        effort = "Moderate"
    else:
        value = 50
        route = "third-party route"
        effort = "Moderate"
    return ScoreDimension(
        value=value,
        explanation=(
            f"{effort} application effort: {route} and {requirement_count} "
            f"detected {'requirement' if requirement_count == 1 else 'requirements'}."
        ),
    )


def _role_category(text: str) -> str:
    normalized = text.lower()
    for category, markers in _ROLE_CATEGORIES:
        if any(marker in normalized for marker in markers):
            return category
    return "software"


def _technology_names(
    text: str,
    profile_skills: dict[str, str] | None = None,
) -> set[str]:
    normalized = text.lower()
    names = {**_KNOWN_TECHNOLOGIES, **(profile_skills or {})}
    return {
        display
        for marker, display in names.items()
        if re.search(rf"(?<![\w+]){re.escape(marker)}(?![\w+])", normalized)
    }


def _human_list(values: list[str]) -> str:
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def _queue_summary(
    count: int,
    minimum_target: int,
    shortfall: int,
    criteria: QueueCriteria,
) -> str:
    if shortfall:
        return (
            f"{count} candidates meet the current criteria; {shortfall} fewer "
            f"than the {minimum_target}-candidate target."
        )
    if criteria == QueueCriteria(
        minimum_score=DEFAULT_MINIMUM_SCORE,
        include_maybe=False,
    ):
        return (
            f"{count} candidates meet the current criteria and the daily target "
            "without lowering thresholds."
        )
    return (
        f"{count} candidates meet the displayed user-selected criteria and the "
        "daily target."
    )


def _expansion_levers(
    scored: list[ScoredOpportunity],
    criteria: QueueCriteria,
    shortfall: int,
) -> list[ExpansionLever]:
    if not shortfall:
        return []
    levers: list[ExpansionLever] = []
    if not criteria.include_maybe and any(
        opportunity.screening.lane == "maybe" for opportunity in scored
    ):
        levers.append(
            ExpansionLever(
                id="include_maybe",
                label="Include manual-review matches",
                description=(
                    "Add scored maybe-lane opportunities without changing hard-reject rules."
                ),
                criteria=criteria.model_copy(update={"include_maybe": True}),
            )
        )
    if criteria.minimum_score > 0:
        lower_score = max(0, criteria.minimum_score - 10)
        levers.append(
            ExpansionLever(
                id="minimum_score",
                label=f"Lower the quality threshold to {lower_score}",
                description=(
                    f"Include opportunities scoring {lower_score}–"
                    f"{criteria.minimum_score - 1}; eligibility rules stay unchanged."
                ),
                criteria=criteria.model_copy(update={"minimum_score": lower_score}),
            )
        )
    return levers
