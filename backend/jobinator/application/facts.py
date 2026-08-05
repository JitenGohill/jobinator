from __future__ import annotations

from dataclasses import dataclass

from jobinator.application.models import CanonicalFact, FactId, FactKind
from jobinator.discovery.models import ScoredOpportunity
from jobinator.profile.models import CanonicalProfile


@dataclass(frozen=True)
class FactCatalog:
    facts: tuple[CanonicalFact, ...]

    @classmethod
    def build(
        cls,
        profile: CanonicalProfile,
        opportunity: ScoredOpportunity,
    ) -> FactCatalog:
        builder = _FactCatalogBuilder()
        builder.add("profile.base_cv", "base_cv", profile.base_cv)
        for project_index, project in enumerate(profile.projects):
            group = project.name
            prefix = f"profile.projects.{project_index}"
            builder.add(f"{prefix}.name", "project_name", project.name, group)
            builder.add(f"{prefix}.summary", "project_summary", project.summary, group)
            for index, highlight in enumerate(project.highlights):
                builder.add(
                    f"{prefix}.highlights.{index}",
                    "project_highlight",
                    highlight,
                    group,
                )
            for index, technology in enumerate(project.technologies):
                builder.add(
                    f"{prefix}.technologies.{index}",
                    "project_technology",
                    technology,
                    group,
                )
        for index, skill in enumerate(profile.skills):
            builder.add(f"profile.skills.{index}", "skill", skill.name)
        for index, stack in enumerate(profile.preferred_stack):
            builder.add(f"profile.preferred_stack.{index}", "skill", stack)
        for work_index, experience in enumerate(profile.work_history):
            group = f"{experience.title} at {experience.employer}"
            prefix = f"profile.work_history.{work_index}"
            builder.add(f"{prefix}.employer", "work_employer", experience.employer, group)
            builder.add(f"{prefix}.title", "work_title", experience.title, group)
            for index, highlight in enumerate(experience.highlights):
                builder.add(
                    f"{prefix}.highlights.{index}",
                    "work_highlight",
                    highlight,
                    group,
                )
        for education_index, education in enumerate(profile.education):
            group = education.institution
            prefix = f"profile.education.{education_index}"
            builder.add(
                f"{prefix}.credential",
                "education",
                " ".join(
                    value
                    for value in (education.credential, education.field_of_study)
                    if value
                ),
                group,
            )
            for index, highlight in enumerate(education.highlights):
                builder.add(
                    f"{prefix}.highlights.{index}",
                    "education_highlight",
                    highlight,
                    group,
                )
        for index, sample in enumerate(profile.writing_samples):
            builder.add(
                f"profile.writing_samples.{index}",
                "writing_sample",
                sample.content,
                sample.title,
            )
        for story_index, story in enumerate(profile.reusable_stories):
            for field in ("situation", "task", "action", "result"):
                builder.add(
                    f"profile.reusable_stories.{story_index}.{field}",
                    "reusable_story",
                    getattr(story, field),
                    story.title,
                )
        for index, constraint in enumerate(profile.constraints):
            builder.add(f"profile.constraints.{index}", "constraint", constraint)
        for field, value in (
            ("company", opportunity.company),
            ("title", opportunity.title),
            ("location", opportunity.location),
            ("description", opportunity.description_text),
            ("apply_url", opportunity.preferred_apply_url),
        ):
            builder.add(f"job.{field}", "job", value)
        return cls(facts=tuple(builder.facts))

    def text(self, fact_id: FactId) -> str | None:
        return next((fact.text for fact in self.facts if fact.id == fact_id), None)

    def profile_evidence(self) -> tuple[str, ...]:
        return tuple(fact.text for fact in self.facts if fact.kind != "job")

    def select(self, fact_ids: list[FactId]) -> tuple[list[str], list[FactId]]:
        selected: list[str] = []
        invalid: list[FactId] = []
        seen: set[FactId] = set()
        for fact_id in fact_ids:
            if fact_id in seen:
                continue
            seen.add(fact_id)
            text = self.text(fact_id)
            if text is None:
                invalid.append(fact_id)
            else:
                selected.append(text)
        return selected, invalid


class _FactCatalogBuilder:
    def __init__(self) -> None:
        self.facts: list[CanonicalFact] = []

    def add(
        self,
        fact_id: str,
        kind: FactKind,
        text: str,
        group: str | None = None,
    ) -> None:
        if text:
            self.facts.append(
                CanonicalFact(id=FactId(fact_id), kind=kind, text=text, group=group)
            )
