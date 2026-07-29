from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def validate_profile_date(value: str) -> str:
    if not re.fullmatch(r"(?:\d{4}-(?:0[1-9]|1[0-2])|present)?", value):
        raise ValueError("Use YYYY-MM, present, or leave the date blank.")
    return value


def validate_profile_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Use a complete http:// or https:// URL.")
    return value


ProfileDate = Annotated[str, AfterValidator(validate_profile_date)]
ProfileUrl = Annotated[str, AfterValidator(validate_profile_url)]


class ProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Project(ProfileModel):
    name: str = Field(min_length=1)
    summary: str
    highlights: list[str]
    technologies: list[str]
    link: ProfileUrl | None = None


class Skill(ProfileModel):
    name: str = Field(min_length=1)
    proficiency: Literal["beginner", "intermediate", "advanced", "expert"]


class Education(ProfileModel):
    institution: str = Field(min_length=1)
    credential: str
    field_of_study: str
    start_date: ProfileDate
    end_date: ProfileDate
    highlights: list[str]


class WorkExperience(ProfileModel):
    employer: str = Field(min_length=1)
    title: str = Field(min_length=1)
    start_date: ProfileDate
    end_date: ProfileDate
    highlights: list[str]


class ProfileLink(ProfileModel):
    label: str = Field(min_length=1)
    url: ProfileUrl


class WritingSample(ProfileModel):
    title: str = Field(min_length=1)
    content: str


class ReusableStory(ProfileModel):
    title: str = Field(min_length=1)
    situation: str
    task: str
    action: str
    result: str


class CanonicalProfile(ProfileModel):
    base_cv: str
    projects: list[Project]
    skills: list[Skill]
    preferred_stack: list[str]
    education: list[Education]
    work_history: list[WorkExperience]
    links: list[ProfileLink]
    constraints: list[str]
    writing_samples: list[WritingSample]
    reusable_stories: list[ReusableStory]

    def known_technology_names(self) -> set[str]:
        return {
            value.lower()
            for value in (
                *self.preferred_stack,
                *(skill.name for skill in self.skills),
                *(technology for project in self.projects for technology in project.technologies),
            )
        }


class SavedProfile(ProfileModel):
    profile: CanonicalProfile
    version: int = Field(ge=1)
    updated_at: datetime


class SaveProfileRequest(ProfileModel):
    profile: CanonicalProfile
    expected_version: int | None = Field(default=None, ge=1)
