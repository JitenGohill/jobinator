from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from jobinator.application.facts import FactCatalog
from jobinator.application.matching import match_profile
from jobinator.application.models import (
    ApplicationPacket,
    ApplicationPacketRequest,
    FactId,
    GeneratedApplicationPlan,
    GenerationDetails,
    ScreeningAnswer,
)
from jobinator.application.provider import ApplicationGenerationInput
from jobinator.application.risk import estimated_effort, review_known_risks
from jobinator.application.runtime import ApplicationGenerationRuntime
from jobinator.database import ApplicationPacketRow
from jobinator.discovery.module import DiscoveryModule
from jobinator.profile.models import CanonicalProfile
from jobinator.profile.module import ProfileModule


class QueuedOpportunityNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class _RenderedDrafts:
    tailored_cv: str
    cover_letter: str | None
    screening_answers: list[ScreeningAnswer]
    invalid_fact_ids: list[FactId]
    invalid_question_indices: list[int]


class ApplicationPacketModule:
    def __init__(
        self,
        profile_module: ProfileModule,
        discovery_module: DiscoveryModule,
        generation_runtime: ApplicationGenerationRuntime,
        sessions: sessionmaker[Session],
    ) -> None:
        self._profile_module = profile_module
        self._discovery_module = discovery_module
        self._generation_runtime = generation_runtime
        self._sessions = sessions

    async def generate_packet(
        self,
        opportunity_id: int,
        request: ApplicationPacketRequest,
    ) -> ApplicationPacket:
        saved_profile = self._profile_module.get_profile()
        profile = saved_profile.profile
        queue = self._discovery_module.build_daily_queue(
            minimum_score=60,
            include_maybe=False,
        )
        opportunity = next(
            (candidate for candidate in queue.candidates if candidate.id == opportunity_id),
            None,
        )
        if opportunity is None:
            raise QueuedOpportunityNotFoundError

        snapshot_id = opportunity.snapshots[0].id
        if snapshot_id is None:
            raise ValueError("Application packets require a persisted job snapshot.")
        request_payload = request.model_dump(mode="json")
        generation_key = ":".join(
            (
                self._generation_runtime.provider.name,
                self._generation_runtime.provider.model,
                self._generation_runtime.prompt_version,
            )
        )
        with self._sessions() as session:
            existing_rows = session.scalars(
                select(ApplicationPacketRow).where(
                    ApplicationPacketRow.snapshot_id == snapshot_id,
                    ApplicationPacketRow.profile_version == saved_profile.version,
                    ApplicationPacketRow.generation_key == generation_key,
                )
            ).all()
            existing = next(
                (row for row in existing_rows if row.request_payload == request_payload),
                None,
            )
            if existing is not None:
                return ApplicationPacket(
                    id=existing.id,
                    profile_version=existing.profile_version,
                    **existing.payload,
                )

        catalog = FactCatalog.build(profile, opportunity)
        context, missing = match_profile(profile, opportunity, catalog)
        cover_letter_useful = "cover letter" in opportunity.description_text.lower()
        generation_input = ApplicationGenerationInput(
            profile=profile,
            opportunity=opportunity,
            matched_context=context,
            missing_requirements=missing,
            request=request,
            cover_letter_useful=cover_letter_useful,
            available_facts=catalog.facts,
        )
        plan = await self._generation_runtime.provider.generate(
            generation_input,
            self._generation_runtime.prompt,
        )
        drafts = _render_plan(
            plan,
            catalog,
            profile,
            opportunity.company,
            opportunity.title,
            request,
            cover_letter_useful,
        )
        rendered_text = "\n".join(
            (
                drafts.tailored_cv,
                drafts.cover_letter or "",
                *(answer.draft for answer in drafts.screening_answers),
            )
        )
        packet = ApplicationPacket(
            id=1,
            profile_version=saved_profile.version,
            opportunity_id=opportunity_id,
            score=opportunity.score,
            job_snapshot=opportunity.snapshots[0],
            tailored_cv_draft=drafts.tailored_cv,
            matched_profile_context=context,
            missing_requirements=missing,
            risk_flags=review_known_risks(
                profile,
                opportunity,
                missing,
                request,
                rendered_text,
                drafts.invalid_fact_ids,
                drafts.invalid_question_indices,
            ),
            direct_apply_link=opportunity.preferred_apply_url,
            estimated_application_effort=estimated_effort(opportunity),
            cover_letter=drafts.cover_letter,
            screening_answers=drafts.screening_answers,
            generation=GenerationDetails(
                provider=self._generation_runtime.provider.name,
                model=self._generation_runtime.provider.model,
                prompt_version=self._generation_runtime.prompt_version,
            ),
        )
        with self._sessions.begin() as session:
            row = ApplicationPacketRow(
                opportunity_id=opportunity_id,
                snapshot_id=snapshot_id,
                profile_version=saved_profile.version,
                request_payload=request_payload,
                generation_key=generation_key,
                payload=packet.model_dump(mode="json", exclude={"id", "profile_version"}),
                created_at=datetime.now(timezone.utc),
            )
            session.add(row)
            session.flush()
            packet_id = row.id
        return packet.model_copy(update={"id": packet_id})


def _render_plan(
    plan: GeneratedApplicationPlan,
    catalog: FactCatalog,
    profile: CanonicalProfile,
    company: str,
    title: str,
    request: ApplicationPacketRequest,
    cover_letter_useful: bool,
) -> _RenderedDrafts:
    selected_cv_facts, invalid_fact_ids = catalog.select(plan.selected_fact_ids)
    selected_cv_facts = [fact for fact in selected_cv_facts if fact != profile.base_cv]
    tailored_cv = "\n\n".join(
        (
            f"Role-specific summary for {title}: {profile.base_cv}",
            *selected_cv_facts,
        )
    )

    cover_letter = None
    cover_facts, invalid_cover_fact_ids = catalog.select(plan.cover_letter_fact_ids)
    invalid_fact_ids.extend(invalid_cover_fact_ids)
    cover_allowed = request.cover_letter_requested or cover_letter_useful
    if cover_allowed:
        if not cover_facts:
            cover_facts = [
                profile.writing_samples[0].content
                if profile.writing_samples
                else profile.base_cv
            ]
        cover_letter = "\n\n".join(
            (
                f"Dear {company} hiring team,",
                *cover_facts,
                f"I am applying for the {title} role.",
            )
        )
    elif plan.cover_letter_fact_ids:
        invalid_fact_ids.extend(plan.cover_letter_fact_ids)

    answer_plans = {answer.question_index: answer for answer in plan.screening_answers}
    invalid_question_indices = sorted(
        {
            answer.question_index
            for answer in plan.screening_answers
            if answer.question_index >= len(request.screening_questions)
        }
    )
    screening_answers: list[ScreeningAnswer] = []
    for index, question in enumerate(request.screening_questions):
        answer_plan = answer_plans.get(index)
        fact_ids = answer_plan.fact_ids if answer_plan is not None else []
        answer_facts, invalid_answer_fact_ids = catalog.select(fact_ids)
        invalid_fact_ids.extend(invalid_answer_fact_ids)
        draft = (
            " ".join(answer_facts)
            if answer_facts
            else "Insufficient canonical-profile evidence to draft an answer."
        )
        screening_answers.append(
            ScreeningAnswer(question=question, draft=draft)
        )
    return _RenderedDrafts(
        tailored_cv=tailored_cv,
        cover_letter=cover_letter,
        screening_answers=screening_answers,
        invalid_fact_ids=invalid_fact_ids,
        invalid_question_indices=invalid_question_indices,
    )
