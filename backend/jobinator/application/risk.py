from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from jobinator.application.models import (
    ApplicationPacketRequest,
    FactId,
    RiskFlag,
)
from jobinator.discovery.models import ScoredOpportunity
from jobinator.profile.models import CanonicalProfile


def estimated_effort(
    opportunity: ScoredOpportunity,
) -> Literal["low", "moderate", "high"]:
    value = opportunity.score.application_effort.value
    if value >= 90:
        return "low"
    if value >= 60:
        return "moderate"
    return "high"


def review_known_risks(
    profile: CanonicalProfile,
    opportunity: ScoredOpportunity,
    missing_requirements: list[str],
    request: ApplicationPacketRequest,
    rendered_text: str,
    invalid_fact_ids: list[FactId],
    invalid_question_indices: list[int],
) -> list[RiskFlag]:
    flags = [
        RiskFlag(
            category="missing_requirement",
            message=f"No canonical-profile evidence was found for: {requirement}.",
        )
        for requirement in missing_requirements
    ]
    required_years = _required_experience_years(opportunity.description_text)
    if (
        required_years is not None
        and _work_history_months(profile, opportunity.fetched_at) < required_years * 12
    ):
        duration = f"{required_years} {'year' if required_years == 1 else 'years'}"
        flags.append(
            RiskFlag(
                category="unsupported_experience",
                message=(
                    f"The role asks for {duration} of experience; the dated "
                    "work history does not establish that duration."
                ),
            )
        )
    flags.extend(_authorization_and_location_risks(profile, opportunity))
    if request.screening_questions:
        flags.append(
            RiskFlag(
                category="manual_review_required",
                message="All custom screening answers require human review before use.",
            )
        )
    if invalid_fact_ids or invalid_question_indices:
        flags.append(
            RiskFlag(
                category="possible_overstatement",
                message=(
                    "The provider selected unknown facts or questions; those selections "
                    "were omitted from the rendered drafts."
                ),
            )
        )
    inflated_terms = re.findall(
        r"\b(?:world-class|unmatched|perfect fit|exceptional|expert)\b",
        rendered_text,
        re.IGNORECASE,
    )
    if inflated_terms:
        flags.extend(
            [
                RiskFlag(
                    category="possible_overstatement",
                    message="Draft writing contains claims that may overstate profile evidence.",
                ),
                RiskFlag(
                    category="generic_or_inflated_writing",
                    message=(
                        "Draft writing uses generic or inflated language: "
                        f"{', '.join(sorted(set(term.lower() for term in inflated_terms)))}."
                    ),
                ),
            ]
        )
    return flags


def _authorization_and_location_risks(
    profile: CanonicalProfile,
    opportunity: ScoredOpportunity,
) -> list[RiskFlag]:
    risks: list[RiskFlag] = []
    posting_text = opportunity.description_text.lower()
    constraints = "\n".join(profile.constraints).lower()
    posting_has_requirement = bool(
        re.search(r"\b(?:authoriz|sponsorship|citizen)", posting_text)
    )
    profile_confirms_authorization = bool(
        re.search(
            r"\b(?:authoriz(?:ed|ation).{0,40}(?:work|without sponsorship)"
            r"|(?:no|without) sponsorship required)\b",
            constraints,
        )
    )
    profile_needs_sponsorship = bool(
        re.search(r"\b(?:need|needs|require|requires).{0,20}sponsorship\b", constraints)
    )
    posting_refuses_sponsorship = bool(
        re.search(r"\b(?:without|no).{0,20}sponsorship\b", posting_text)
    )
    if posting_has_requirement and (
        not profile_confirms_authorization
        or (profile_needs_sponsorship and posting_refuses_sponsorship)
    ):
        risks.append(
            RiskFlag(
                category="authorization_or_location_mismatch",
                message=(
                    "The posting's authorization or sponsorship requirement is not "
                    "satisfied by the canonical profile constraints."
                ),
            )
        )
    if _location_conflicts_with_constraints(opportunity.location, constraints):
        risks.append(
            RiskFlag(
                category="authorization_or_location_mismatch",
                message=(
                    f"The role location ({opportunity.location}) is not established as "
                    "acceptable by the canonical profile constraints."
                ),
            )
        )
    return risks


def _required_experience_years(description: str) -> int | None:
    match = re.search(
        r"\b(\d+)\+?\s+years?(?:\s+of)?\s+"
        r"(?:(?:software engineering|engineering|development)\s+)?experience\b",
        description,
        re.IGNORECASE,
    )
    return int(match.group(1)) if match is not None else None


def _work_history_months(profile: CanonicalProfile, as_of: datetime) -> int:
    worked_months: set[int] = set()
    for experience in profile.work_history:
        if not experience.start_date or not experience.end_date:
            continue
        start_year, start_month = map(int, experience.start_date.split("-"))
        if experience.end_date == "present":
            end_year, end_month = as_of.year, as_of.month
        else:
            end_year, end_month = map(int, experience.end_date.split("-"))
        start = start_year * 12 + start_month
        end = end_year * 12 + end_month
        worked_months.update(range(start, end + 1))
    return len(worked_months)


def _location_conflicts_with_constraints(location: str, constraints: str) -> bool:
    location_lower = location.lower()
    known_locations = ("new york", "chicago", "remote")
    constrained_locations = {
        marker for marker in known_locations if marker in constraints
    }
    if not constrained_locations:
        return False
    if "new york" in location_lower:
        return "new york" not in constrained_locations
    if "chicago" in location_lower:
        return "chicago" not in constrained_locations
    if "remote" in location_lower:
        return "remote" not in constrained_locations
    return True
