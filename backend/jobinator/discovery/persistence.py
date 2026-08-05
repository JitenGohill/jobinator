from jobinator.database import JobSnapshotRow
from jobinator.discovery.models import JobSnapshot


def snapshot_row(snapshot: JobSnapshot) -> JobSnapshotRow:
    return JobSnapshotRow(
        source_url=snapshot.source_url,
        fetched_at=snapshot.fetched_at,
        company=snapshot.company,
        title=snapshot.title,
        location=snapshot.location,
        description_text=snapshot.description_text,
        detected_requirements=snapshot.detected_requirements,
        source_platform=snapshot.source_platform,
        ats_posting_id=snapshot.ats_posting_id,
        canonical_url=snapshot.canonical_url,
        raw_posting=snapshot.raw_posting,
    )
