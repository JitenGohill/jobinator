from __future__ import annotations

import re
from typing import Literal, NewType

from pydantic import BaseModel, ConfigDict, Field, field_validator

from jobinator.discovery.models import JobSnapshot, OpportunityScore


class ApplicationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApplicationPacketRequest(ApplicationModel):
    cover_letter_requested: bool = False
    screening_questions: list[str] = Field(default_factory=list)

    @field_validator("screening_questions")
    @classmethod
    def reject_legal_and_demographic_questions(cls, questions: list[str]) -> list[str]:
        protected_markers = (
            "citizen",
            "citizenship",
            "authorized to work",
            "authorised to work",
            "work authorization",
            "sponsorship",
            "visa",
            "race",
            "ethnicity",
            "gender",
            "sexual orientation",
            "disability",
            "disabled",
            "veteran",
            "date of birth",
            "birth date",
            "how old",
            "your age",
            "religion",
            "marital",
            "pregnant",
            "criminal",
            "conviction",
        )
        for question in questions:
            normalized = " ".join(re.findall(r"[a-z]+", question.casefold()))
            padded = f" {normalized} "
            if any(f" {marker} " in padded for marker in protected_markers):
                raise ValueError("Legal and demographic screening answers are not drafted.")
        return questions


class MatchedProfileContext(ApplicationModel):
    skills: list[str]
    projects: list[str]
    work_experience: list[str]


class ScreeningAnswer(ApplicationModel):
    question: str
    draft: str
    review_required: Literal[True] = True


FactId = NewType("FactId", str)
FactKind = Literal[
    "base_cv",
    "project_name",
    "project_summary",
    "project_highlight",
    "project_technology",
    "skill",
    "work_employer",
    "work_title",
    "work_highlight",
    "education",
    "education_highlight",
    "writing_sample",
    "reusable_story",
    "constraint",
    "job",
]


class CanonicalFact(ApplicationModel):
    id: FactId
    kind: FactKind
    text: str = Field(min_length=1)
    group: str | None = None


class ScreeningAnswerPlan(ApplicationModel):
    question_index: int = Field(ge=0)
    fact_ids: list[FactId]


RiskCategory = Literal[
    "possible_overstatement",
    "unsupported_experience",
    "missing_requirement",
    "authorization_or_location_mismatch",
    "generic_or_inflated_writing",
    "manual_review_required",
]


class RiskFlag(ApplicationModel):
    category: RiskCategory
    message: str


class GenerationDetails(ApplicationModel):
    provider: str
    model: str
    prompt_version: str


class GeneratedApplicationPlan(ApplicationModel):
    selected_fact_ids: list[FactId]
    cover_letter_fact_ids: list[FactId]
    screening_answers: list[ScreeningAnswerPlan]


class ApplicationPacket(ApplicationModel):
    id: int = Field(ge=1)
    profile_version: int = Field(ge=1)
    opportunity_id: int
    score: OpportunityScore
    job_snapshot: JobSnapshot
    tailored_cv_draft: str
    matched_profile_context: MatchedProfileContext
    missing_requirements: list[str]
    risk_flags: list[RiskFlag]
    direct_apply_link: str
    estimated_application_effort: Literal["low", "moderate", "high"]
    cover_letter: str | None
    screening_answers: list[ScreeningAnswer]
    generation: GenerationDetails


DocumentType = Literal["cv", "cover_letter"]
ExportFormat = Literal["markdown", "pdf"]


class ExportedDocument(ApplicationModel):
    document_type: DocumentType
    version: int = Field(ge=1)
    preview_markdown: str
    markdown_url: str
    pdf_url: str


class ExportBundle(ApplicationModel):
    packet_id: int = Field(ge=1)
    profile_version: int = Field(ge=1)
    job_snapshot_id: int = Field(ge=1)
    documents: list[ExportedDocument]
