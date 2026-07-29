from __future__ import annotations

import re
from datetime import datetime

from jobinator.discovery.models import JobSnapshot, ScreeningLane, ScreeningResult
from jobinator.profile.models import CanonicalProfile


class ScreeningPolicy:
    """Classify normalized opportunities before they enter scoring."""

    _TARGET_ROLE_TYPES = (
        ("full-stack", "full-stack engineering"),
        ("full stack", "full-stack engineering"),
        ("backend", "backend engineering"),
        ("platform", "platform engineering"),
        ("internal tools", "internal-tools engineering"),
        ("ai ", "AI-adjacent engineering"),
        ("machine learning", "AI-adjacent engineering"),
    )
    _EXPERIENCE_PATTERN = re.compile(
        r"\b(?P<years>\d+)(?:\s*(?:-|–|to)\s*(?P<max_years>\d+))?\+?\s+years?"
        r"(?:"
        r"(?:\s+of)?\s+(?:professional\s+)?"
        r"(?:software\s+engineering|engineering|development)\s+experience"
        r"|[’']?\s+(?:of\s+)?experience\s+"
        r"(?:in\s+software\s+engineering|(?:developing|building|maintaining)\b)"
        r"|\s+in\s+(?:software\s+)?(?:engineering|development)\b"
        r")",
        re.IGNORECASE,
    )
    _EXCLUDED_ROLE_TYPES = (
        (re.compile(r"\b(?:mobile|ios|android)\b", re.IGNORECASE), "mobile"),
        (re.compile(r"\b(?:qa|quality assurance)\b", re.IGNORECASE), "QA"),
        (re.compile(r"\bit support\b", re.IGNORECASE), "IT support"),
        (re.compile(r"\bdata analyst\b", re.IGNORECASE), "data analyst"),
    )
    _EXCLUDED_SENIORITY = ("senior", "staff", "principal", "manager")
    _KNOWN_STACKS = (
        "angular",
        "c#",
        "c++",
        "django",
        "fastapi",
        "go",
        "golang",
        "java",
        "javascript",
        "kotlin",
        ".net",
        "node",
        "php",
        "python",
        "rails",
        "react",
        "ruby",
        "rust",
        "scala",
        "swift",
        "typescript",
        "vue",
    )

    def __init__(self, profile: CanonicalProfile | None = None) -> None:
        self._profile = profile

    def screen(self, snapshot: JobSnapshot) -> ScreeningResult:
        reasons: list[str] = []
        role_reason = self._role_reason(snapshot)
        if role_reason is not None:
            reasons.append(role_reason)
        location_reason = self._location_reason(snapshot)
        if location_reason is not None:
            reasons.append(location_reason)

        experience_years = self._experience_years(snapshot)
        hard_reasons = self._hard_reject_reasons(snapshot, experience_years)
        if hard_reasons:
            return ScreeningResult(lane="rejected", reasons=[*reasons, *hard_reasons])

        lane: ScreeningLane = "eligible"
        if experience_years == 3:
            lane = "stretch"
            reasons.append("Stretch experience requirement: 3 years.")
        elif experience_years is not None and experience_years >= 4:
            lane = "stretch"
            reasons.append(
                f"Stretch experience requirement: {experience_years} years, with an "
                "accepted junior-equivalent path."
            )
        elif experience_years is not None:
            reasons.append(
                f"Junior-friendly experience requirement: {experience_years} "
                f"{'year' if experience_years == 1 else 'years'}."
            )
        else:
            junior_role_reason = self._junior_role_reason(snapshot)
            if junior_role_reason is not None:
                reasons.append(junior_role_reason)

        if self._is_exceptional_agency_listing(snapshot):
            lane = "maybe"
            reasons.append(
                "Staffing-agency listing retained for manual review because it is a "
                "direct-hire role with a named client and compensation."
            )
        elif self._is_exceptional_unclear_employer_listing(snapshot):
            lane = "maybe"
            reasons.append(
                "Unclear-employer listing retained for manual review because it is a "
                "direct-hire role with compensation and detailed requirements."
            )
        return ScreeningResult(lane=lane, reasons=reasons)

    def _hard_reject_reasons(
        self,
        snapshot: JobSnapshot,
        experience_years: int | None,
    ) -> list[str]:
        title = snapshot.title
        text = snapshot.description_text
        normalized_title = title.lower()
        normalized_text = text.lower()
        reasons: list[str] = []

        if self._role_reason(snapshot) is None:
            reasons.append("Outside target software engineering role types.")
        if self._location_reason(snapshot) is None:
            reasons.append(f"Outside target locations: {snapshot.location}.")
        if (
            re.search(
                r"\b(?:must relocate to|relocation to .{1,40}? is required)\b",
                normalized_text,
            )
            and not re.search(
                r"\b(?:must relocate to|relocation to)\s+(?:new york|chicago)\b",
                normalized_text,
            )
        ):
            reasons.append("Requires relocation outside New York or Chicago.")

        combined_role_text = f"{normalized_title}\n{normalized_text}"
        has_non_frontend_target = bool(
            re.search(
                r"\b(?:back[\s-]?end|full[\s-]?stack|platform|internal tools|"
                r"ai[\s-]adjacent|machine learning)\b",
                combined_role_text,
            )
        )
        frontend_title = re.search(r"\bfront[\s-]?end\b", normalized_title)
        frontend_only_description = re.search(
            r"\b(?:this is|the position is|the role is)\s+(?:an?\s+)?"
            r"(?:pure(?:ly)?[\s-]+)?front[\s-]?end(?:[\s-]+only)?\s+role\b",
            normalized_text,
        )
        if (frontend_title or frontend_only_description) and not has_non_frontend_target:
            reasons.append("Excluded role type: pure frontend.")
        for pattern, label in self._EXCLUDED_ROLE_TYPES:
            title_match = pattern.search(normalized_title)
            description_role_pattern = pattern.pattern.removeprefix(r"\b").removesuffix(r"\b")
            description_match = re.search(
                rf"\b(?:this is|the position is|the role is)\s+(?:an?\s+)?"
                rf"(?:pure(?:ly)?[\s-]+)?{description_role_pattern}"
                r"(?:[\s-]+only)?\s+role\b",
                normalized_text,
                re.IGNORECASE,
            )
            if title_match or description_match:
                reasons.append(f"Excluded role type: {label}.")
                break
        if "intern" in normalized_title and "unpaid" in normalized_text:
            reasons.append("Excluded role type: unpaid internship.")

        for seniority in self._EXCLUDED_SENIORITY:
            title_match = re.search(rf"\b{seniority}\b", normalized_title)
            description_match = re.search(
                rf"\b(?:this is|seeking|hiring for)\s+(?:an?\s+)?{seniority}"
                rf"(?:[\s-]+level)?\s+role\b",
                normalized_text,
            )
            if title_match or description_match:
                reasons.append(f"Excluded seniority: {seniority} role.")
                break

        if (
            experience_years is not None
            and experience_years >= 4
            and not self._accepts_junior_equivalent(normalized_text)
        ):
            reasons.append(
                "Experience requirement is 4+ years without an accepted junior-equivalent path."
            )
        if re.search(
            r"\b(?:unpaid\s+(?:role|position|internship)|(?:role|position|internship)"
            r"\s+is\s+unpaid)\b",
            normalized_text,
        ):
            reasons.append("Compensation is explicitly unpaid.")
        if re.search(r"\bcommission[\s-]+only\b", normalized_text):
            reasons.append("Compensation is commission-only.")
        if re.search(
            r"\b(?:active|current)\s+"
            r"(?:(?:(?:top\s+)?secret|ts/sci)\s+)?(?:security\s+)?clearance\b",
            normalized_text,
        ):
            reasons.append("Requires an active security clearance.")
        if self._deadline_has_passed(snapshot):
            reasons.append("Application deadline has passed.")

        incompatible_stack = self._incompatible_professional_stack(normalized_text)
        if incompatible_stack is not None:
            reasons.append(
                f"Requires professional {incompatible_stack} experience that is absent "
                "from the canonical profile."
            )

        if self._is_agency_listing(snapshot) and not self._is_exceptional_agency_listing(snapshot):
            reasons.append("Staffing-agency listing rejected by default.")
        has_unclear_employer = self._has_unclear_employer(snapshot)
        exceptional_unclear_employer = self._is_exceptional_unclear_employer_listing(snapshot)
        if has_unclear_employer and not exceptional_unclear_employer:
            reasons.append("Employer identity is unclear.")
        return reasons

    def _role_reason(self, snapshot: JobSnapshot) -> str | None:
        title = snapshot.title.lower()
        for marker, label in self._TARGET_ROLE_TYPES:
            if marker in title:
                return f"Target role type: {label}."
        if (
            "software engineer" in title
            or "software developer" in title
            or "software development engineer" in title
        ):
            return "Target role type: software engineering."
        if "api engineer" in title:
            return "Target role type: backend engineering."
        if "engineer" in title or "developer" in title:
            description = snapshot.description_text.lower()
            for marker, label in self._TARGET_ROLE_TYPES:
                if marker in description:
                    return f"Target role type: {label}."
            if re.search(
                r"\b(?:build|develop|maintain)(?:ing|s)?\s+(?:backend\s+)?apis?\b",
                description,
            ):
                return "Target role type: backend engineering."
        return None

    @staticmethod
    def _location_reason(snapshot: JobSnapshot) -> str | None:
        location = snapshot.location.lower()
        if "new york" in location or "nyc" in location:
            return "Target location: New York."
        if "chicago" in location:
            return "Target location: Chicago."
        if "remote" in location and re.search(
            r"\b(?:us|u\.s\.|usa|united states)\b",
            location,
        ):
            return "Target location: US-based remote."
        if "remote" in location and re.search(
            r"\b(?:based in|within|limited to)(?: candidates)?(?: based)? in the united states\b",
            snapshot.description_text,
            re.IGNORECASE,
        ):
            return "Target location: US-based remote."
        return None

    def _experience_years(self, snapshot: JobSnapshot) -> int | None:
        match = self._EXPERIENCE_PATTERN.search(snapshot.description_text)
        if match is None:
            return None
        return int(match.group("max_years") or match.group("years"))

    @staticmethod
    def _junior_role_reason(snapshot: JobSnapshot) -> str | None:
        text = f"{snapshot.title}\n{snapshot.description_text}".lower()
        labels = (
            (r"\bentry[\s-]level\b", "entry-level"),
            (r"\bnew[\s-]grad\b", "new grad"),
            (r"\bapprentic(?:e|eship)\b", "apprenticeship"),
            (r"\bjunior\b", "junior"),
        )
        for pattern, label in labels:
            if re.search(pattern, text):
                return f"Junior-friendly role: {label}."
        return None

    @staticmethod
    def _accepts_junior_equivalent(normalized_text: str) -> bool:
        return bool(
            re.search(
                r"(?:equivalent|in place of).{0,60}\b(?:project|bootcamp|internship)\b"
                r"|\b(?:project|bootcamp|internship)\b.{0,60}(?:equivalent|accepted)",
                normalized_text,
            )
        )

    @staticmethod
    def _deadline_has_passed(snapshot: JobSnapshot) -> bool:
        if "applications closed" in snapshot.description_text.lower():
            return True
        deadline_patterns = (
            (
                r"\bapplication deadline:\s*([A-Z][a-z]+ \d{1,2}, \d{4})",
                "%B %d, %Y",
            ),
            (r"\b(?:apply by|application deadline:)\s*(\d{4}-\d{2}-\d{2})", "%Y-%m-%d"),
        )
        for pattern, date_format in deadline_patterns:
            match = re.search(pattern, snapshot.description_text, re.IGNORECASE)
            if match is None:
                continue
            try:
                deadline = datetime.strptime(match.group(1), date_format).date()
            except ValueError:
                continue
            return deadline < snapshot.fetched_at.date()
        return False

    def _incompatible_professional_stack(self, normalized_text: str) -> str | None:
        if self._profile is None:
            return None
        profile_stack = self._profile.known_technology_names()
        for stack in self._KNOWN_STACKS:
            escaped_stack = re.escape(stack)
            requires_stack = re.search(
                rf"\bprofessional experience (?:with|in) {escaped_stack}\b"
                rf"|\b\d+\+?\s+years? of professional {escaped_stack} experience\b",
                normalized_text,
            )
            if requires_stack and stack not in profile_stack:
                return stack.title() if stack != ".net" else ".NET"
        return None

    @staticmethod
    def _is_agency_listing(snapshot: JobSnapshot) -> bool:
        description = snapshot.description_text.lower()
        return bool(
            re.search(
                r"\b(?:staffing (?:agency|firm)|recruit(?:ing|ment) agency)\b",
                description,
            )
        )

    @staticmethod
    def _is_exceptional_agency_listing(snapshot: JobSnapshot) -> bool:
        description = snapshot.description_text.lower()
        has_named_client = bool(
            re.search(
                r"\bclient\s+(?!is\b|name\b|unnamed\b|undisclosed\b|confidential\b)[a-z]",
                description,
            )
        )
        return (
            ScreeningPolicy._is_agency_listing(snapshot)
            and bool(re.search(r"\bdirect[\s-]+hire\b", description))
            and has_named_client
            and ScreeningPolicy._has_compensation(description)
        )

    @staticmethod
    def _is_exceptional_unclear_employer_listing(snapshot: JobSnapshot) -> bool:
        description = snapshot.description_text.lower()
        return (
            ScreeningPolicy._has_unclear_employer(snapshot)
            and bool(re.search(r"\bdirect[\s-]+hire\b", description))
            and ScreeningPolicy._has_compensation(description)
            and bool(snapshot.detected_requirements)
        )

    @staticmethod
    def _has_unclear_employer(snapshot: JobSnapshot) -> bool:
        description = snapshot.description_text.lower()
        return bool(
            re.search(
                r"\b(?:employer is confidential|confidential (?:client|employer|company)"
                r"|(?:client|employer|company) is undisclosed|undisclosed "
                r"(?:client|employer|company)|company not disclosed)\b",
                description,
            )
        )

    @staticmethod
    def _has_compensation(description: str) -> bool:
        return bool(
            re.search(
                r"\b(?:salary|compensation|pay range)\b|\$\s*\d[\d,]*(?:\s*-\s*\$?\d[\d,]*)?",
                description,
            )
        )
