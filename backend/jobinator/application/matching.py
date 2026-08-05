from __future__ import annotations

import re

from jobinator.application.facts import FactCatalog
from jobinator.application.models import MatchedProfileContext
from jobinator.discovery.models import ScoredOpportunity
from jobinator.profile.models import CanonicalProfile

_REQUIREMENT_STOPWORDS = {
    "a",
    "an",
    "and",
    "building",
    "experience",
    "in",
    "of",
    "required",
    "skills",
    "the",
    "with",
    "years",
}


def match_profile(
    profile: CanonicalProfile,
    opportunity: ScoredOpportunity,
    catalog: FactCatalog,
) -> tuple[MatchedProfileContext, list[str]]:
    known = profile.known_technologies()
    matched_keys = {
        key
        for requirement in opportunity.detected_requirements
        for key in known
        if _contains_term(requirement, key)
    }
    evidence = catalog.profile_evidence()
    missing = sorted(
        requirement
        for requirement in opportunity.detected_requirements
        if not requirement_supported(requirement, evidence)
    )
    projects = sorted(
        project.name
        for project in profile.projects
        if {technology.lower() for technology in project.technologies} & matched_keys
        or any(
            requirement_supported(
                requirement,
                (
                    project.name,
                    project.summary,
                    *project.highlights,
                    *project.technologies,
                ),
            )
            for requirement in opportunity.detected_requirements
        )
    )
    work_experience = sorted(
        f"{experience.title} at {experience.employer}"
        for experience in profile.work_history
        if experience.title.lower() in opportunity.description_text.lower()
        or any(
            requirement_supported(
                requirement,
                (
                    experience.employer,
                    experience.title,
                    *experience.highlights,
                ),
            )
            for requirement in opportunity.detected_requirements
        )
    )
    return (
        MatchedProfileContext(
            skills=sorted(known[key] for key in matched_keys),
            projects=projects,
            work_experience=work_experience,
        ),
        missing,
    )


def requirement_supported(requirement: str, evidence: tuple[str, ...]) -> bool:
    normalized_requirement = " ".join(requirement.lower().split())
    if any(
        normalized_requirement in " ".join(value.lower().split())
        for value in evidence
    ):
        return True
    required_terms = _meaningful_terms(requirement)
    if not required_terms:
        return False
    coverage = max(
        (
            len(required_terms & _meaningful_terms(value)) / len(required_terms)
            for value in evidence
        ),
        default=0,
    )
    return coverage >= 0.5


def _meaningful_terms(value: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-z0-9+#.]+", value.lower())
        if term not in _REQUIREMENT_STOPWORDS
    }


def _contains_term(text: str, term: str) -> bool:
    return bool(
        re.search(rf"(?<![\w+]){re.escape(term)}(?![\w+])", text.lower())
    )
