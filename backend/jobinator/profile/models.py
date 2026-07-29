from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Project(ProfileModel):
    name: str = Field(min_length=1)
    summary: str
    highlights: list[str]
    technologies: list[str]
    link: str | None = None


class Skill(ProfileModel):
    name: str = Field(min_length=1)
    proficiency: Literal["beginner", "intermediate", "advanced", "expert"]


class Education(ProfileModel):
    institution: str = Field(min_length=1)
    credential: str
    field_of_study: str
    start_date: str
    end_date: str
    highlights: list[str]


class WorkExperience(ProfileModel):
    employer: str = Field(min_length=1)
    title: str = Field(min_length=1)
    start_date: str
    end_date: str
    highlights: list[str]


class ProfileLink(ProfileModel):
    label: str = Field(min_length=1)
    url: str = Field(min_length=1)


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


class SavedProfile(ProfileModel):
    profile: CanonicalProfile
    version: int = Field(ge=1)
    updated_at: datetime


class SaveProfileRequest(ProfileModel):
    profile: CanonicalProfile
    expected_version: int | None = Field(default=None, ge=1)
