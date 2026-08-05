from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from jobinator.database import CanonicalProfileRow, CanonicalProfileVersionRow
from jobinator.profile.models import CanonicalProfile, SavedProfile


class ProfileNotFoundError(Exception):
    pass


class ProfileVersionConflictError(Exception):
    pass


class ProfileModule:
    """Maintain the single canonical profile and its persistence invariants."""

    _PROFILE_ID = 1

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def get_profile(self) -> SavedProfile:
        with self._sessions() as session:
            row = session.get(CanonicalProfileRow, self._PROFILE_ID)
            if row is None:
                raise ProfileNotFoundError
            return self._to_saved_profile(row)

    def save_profile(
        self,
        profile: CanonicalProfile,
        expected_version: int | None,
    ) -> SavedProfile:
        with self._sessions.begin() as session:
            row = session.get(CanonicalProfileRow, self._PROFILE_ID)
            now = datetime.now(timezone.utc)

            if row is None:
                if expected_version is not None:
                    raise ProfileVersionConflictError
                row = CanonicalProfileRow(
                    id=self._PROFILE_ID,
                    version=1,
                    payload=profile.model_dump(mode="json"),
                    updated_at=now,
                )
                session.add(row)
            else:
                if expected_version != row.version:
                    raise ProfileVersionConflictError
                row.version += 1
                row.payload = profile.model_dump(mode="json")
                row.updated_at = now

            session.add(
                CanonicalProfileVersionRow(
                    version=row.version,
                    payload=profile.model_dump(mode="json"),
                    updated_at=now,
                )
            )

            session.flush()
            return self._to_saved_profile(row)

    @staticmethod
    def _to_saved_profile(row: CanonicalProfileRow) -> SavedProfile:
        updated_at = row.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return SavedProfile(
            profile=CanonicalProfile.model_validate(row.payload),
            version=row.version,
            updated_at=updated_at,
        )
