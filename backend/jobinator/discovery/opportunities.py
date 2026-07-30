from __future__ import annotations

import re
from difflib import SequenceMatcher
from enum import IntEnum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from jobinator.discovery.models import JobSnapshot, Opportunity

_COMPANY_SUFFIXES = {"corp", "corporation", "inc", "incorporated", "llc", "ltd", "limited"}
_TITLE_ALIASES = {
    "eng": "engineer",
    "engr": "engineer",
    "jr": "junior",
    "sr": "senior",
}
_TITLE_LEVELS = {
    "intern",
    "junior",
    "senior",
    "staff",
    "principal",
    "lead",
    "i",
    "ii",
    "iii",
    "iv",
}
_REPOST_HOST_MARKERS = ("glassdoor.", "indeed.", "linkedin.", "monster.", "ziprecruiter.")
_ATS_HOST_SUFFIXES = ("ashbyhq.com", "greenhouse.io", "lever.co", "myworkdayjobs.com")
_TRACKING_QUERY_PREFIXES = ("gh_src", "source", "trk", "utm_")
_CANONICAL_URL_WEIGHT = 5
_ATS_POSTING_WEIGHT = 4
_COMPANY_WEIGHT = 2
_TITLE_WEIGHT = 2
_LOCATION_WEIGHT = 1
_EQUIVALENCE_SCORE = 5
_REQUIRED_MATCHING_SIGNALS = 2


class _ApplyRouteAuthority(IntEnum):
    REPOST = 0
    UNKNOWN = 1
    ATS = 2
    OFFICIAL = 3


def build_opportunities(snapshots: list[JobSnapshot]) -> list[Opportunity]:
    groups: list[list[JobSnapshot]] = []
    for snapshot in sorted(snapshots, key=lambda item: item.id or 0):
        matching_group_indexes = [
            index
            for index, group in enumerate(groups)
            if any(_are_equivalent(snapshot, existing) for existing in group)
        ]
        if not matching_group_indexes:
            groups.append([snapshot])
        else:
            first_index = matching_group_indexes[0]
            merged_group = [
                existing
                for index in matching_group_indexes
                for existing in groups[index]
            ]
            merged_group.append(snapshot)
            for index in reversed(matching_group_indexes):
                groups.pop(index)
            groups.insert(first_index, merged_group)

    opportunities = [_to_opportunity(group) for group in groups]
    return sorted(
        opportunities,
        key=lambda opportunity: (
            max(snapshot.fetched_at for snapshot in opportunity.snapshots),
            opportunity.id or 0,
        ),
        reverse=True,
    )


def _are_equivalent(left: JobSnapshot, right: JobSnapshot) -> bool:
    canonical_url_matches = _canonical_url(left.canonical_url) == _canonical_url(
        right.canonical_url
    )
    ats_posting_matches = (
        left.source_platform == right.source_platform
        and left.ats_posting_id is not None
        and left.ats_posting_id == right.ats_posting_id
    )
    company_matches = _normalized_company(left.company) == _normalized_company(right.company)
    title_matches = _titles_are_similar(left.title, right.title)
    location_matches = _normalized_words(left.location) == _normalized_words(right.location)
    matching_signal_count = sum(
        (
            canonical_url_matches,
            ats_posting_matches,
            company_matches,
            title_matches,
            location_matches,
        )
    )
    score = (
        _CANONICAL_URL_WEIGHT * canonical_url_matches
        + _ATS_POSTING_WEIGHT * ats_posting_matches
        + _COMPANY_WEIGHT * company_matches
        + _TITLE_WEIGHT * title_matches
        + _LOCATION_WEIGHT * location_matches
    )
    return (
        score >= _EQUIVALENCE_SCORE
        and matching_signal_count >= _REQUIRED_MATCHING_SIGNALS
    )


def _to_opportunity(snapshots: list[JobSnapshot]) -> Opportunity:
    preferred = max(snapshots, key=_apply_route_rank)
    return Opportunity(
        **preferred.model_dump(),
        preferred_apply_url=preferred.canonical_url,
        snapshots=snapshots,
    )


def _apply_route_rank(snapshot: JobSnapshot) -> tuple[_ApplyRouteAuthority, bool, int]:
    parts = urlsplit(snapshot.canonical_url)
    hostname = (parts.hostname or "").lower()
    if snapshot.source_platform in {"company", "official"}:
        authority = _ApplyRouteAuthority.OFFICIAL
    elif any(hostname.endswith(suffix) for suffix in _ATS_HOST_SUFFIXES):
        authority = _ApplyRouteAuthority.ATS
    elif any(marker in hostname for marker in _REPOST_HOST_MARKERS):
        authority = _ApplyRouteAuthority.REPOST
    else:
        authority = _ApplyRouteAuthority.UNKNOWN
    return authority, not bool(parts.query), -(snapshot.id or 0)


def _canonical_url(value: str) -> str:
    parts = urlsplit(value)
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parts.query)
            if not key.lower().startswith(_TRACKING_QUERY_PREFIXES)
        ]
    )
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            query,
            "",
        )
    )


def _normalized_company(value: str) -> str:
    words = _normalized_words(value).split()
    while words and words[-1] in _COMPANY_SUFFIXES:
        words.pop()
    return " ".join(words)


def _normalized_title(value: str) -> str:
    words = [_TITLE_ALIASES.get(word, word) for word in _normalized_words(value).split()]
    return " ".join(words)


def _titles_are_similar(left: str, right: str) -> bool:
    normalized_left = _normalized_title(left)
    normalized_right = _normalized_title(right)
    left_levels = set(normalized_left.split()) & _TITLE_LEVELS
    right_levels = set(normalized_right.split()) & _TITLE_LEVELS
    if left_levels and right_levels and left_levels != right_levels:
        return False
    return (
        normalized_left == normalized_right
        or SequenceMatcher(None, normalized_left, normalized_right).ratio() >= 0.92
    )


def _normalized_words(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))
