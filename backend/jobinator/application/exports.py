from __future__ import annotations

import io
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from jobinator.application.models import (
    DocumentType,
    ExportBundle,
    ExportedDocument,
    ExportFormat,
)
from jobinator.database import (
    ApplicationPacketRow,
    CanonicalProfileVersionRow,
    DocumentExportRow,
)
from jobinator.profile.models import CanonicalProfile, SavedProfile


class ApplicationPacketNotFoundError(Exception):
    pass


class DocumentExportNotFoundError(Exception):
    pass


class DocumentExportModule:
    """Render private packet documents and keep their version relationships explicit."""

    def __init__(self, sessions: sessionmaker[Session], export_directory: Path) -> None:
        self._sessions = sessions
        self._export_directory = export_directory.resolve()

    def export_packet(self, packet_id: int) -> ExportBundle:
        with self._sessions.begin() as session:
            packet = session.get(ApplicationPacketRow, packet_id)
            if packet is None:
                raise ApplicationPacketNotFoundError

            documents: list[tuple[DocumentType, str]] = [
                ("cv", str(packet.payload["tailored_cv_draft"])),
            ]
            cover_letter = packet.payload.get("cover_letter")
            if cover_letter is not None:
                documents.append(("cover_letter", str(cover_letter)))

            exported = [
                self._write_document(session, packet_id, document_type, content)
                for document_type, content in documents
            ]
            return ExportBundle(
                packet_id=packet.id,
                profile_version=packet.profile_version,
                job_snapshot_id=packet.snapshot_id,
                documents=exported,
            )

    def packet_profile(self, packet_id: int) -> SavedProfile:
        with self._sessions() as session:
            packet = session.get(ApplicationPacketRow, packet_id)
            if packet is None:
                raise ApplicationPacketNotFoundError
            profile = session.get(CanonicalProfileVersionRow, packet.profile_version)
            if profile is None:
                raise ApplicationPacketNotFoundError
            updated_at = profile.updated_at
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            return SavedProfile(
                profile=CanonicalProfile.model_validate(profile.payload),
                version=profile.version,
                updated_at=updated_at,
            )

    def exported_file(
        self,
        packet_id: int,
        document_type: DocumentType,
        version: int,
        export_format: ExportFormat,
    ) -> Path:
        with self._sessions() as session:
            row = session.scalar(
                select(DocumentExportRow).where(
                    DocumentExportRow.packet_id == packet_id,
                    DocumentExportRow.document_type == document_type,
                    DocumentExportRow.version == version,
                )
            )
            if row is None:
                raise DocumentExportNotFoundError
            relative_path = row.markdown_path if export_format == "markdown" else row.pdf_path
        path = (self._export_directory / relative_path).resolve()
        if not path.is_relative_to(self._export_directory) or not path.is_file():
            raise DocumentExportNotFoundError
        return path

    def _write_document(
        self,
        session: Session,
        packet_id: int,
        document_type: DocumentType,
        content: str,
    ) -> ExportedDocument:
        latest_version = session.scalar(
            select(func.max(DocumentExportRow.version)).where(
                DocumentExportRow.packet_id == packet_id,
                DocumentExportRow.document_type == document_type,
            )
        )
        version = (latest_version or 0) + 1
        relative_directory = Path(f"packet-{packet_id}")
        stem = f"{document_type.replace('_', '-')}-v{version}"
        markdown_path = relative_directory / f"{stem}.md"
        pdf_path = relative_directory / f"{stem}.pdf"
        absolute_directory = self._export_directory / relative_directory
        absolute_directory.mkdir(parents=True, exist_ok=True)
        (self._export_directory / markdown_path).write_text(content, encoding="utf-8")
        (self._export_directory / pdf_path).write_bytes(render_pdf(content))
        session.add(
            DocumentExportRow(
                packet_id=packet_id,
                document_type=document_type,
                version=version,
                markdown_path=str(markdown_path),
                pdf_path=str(pdf_path),
                created_at=datetime.now(timezone.utc),
            )
        )
        base_url = (
            f"/api/application-packets/{packet_id}/exports/"
            f"{document_type}/{version}"
        )
        return ExportedDocument(
            document_type=document_type,
            version=version,
            preview_markdown=content,
            markdown_url=f"{base_url}/markdown",
            pdf_url=f"{base_url}/pdf",
        )


def render_pdf(markdown: str) -> bytes:
    """Build a deterministic, multi-page Unicode PDF."""

    lines: list[str] = []
    for source_line in markdown.splitlines() or [""]:
        lines.extend(textwrap.wrap(source_line, width=88) or [""])
    font_name = "JobinatorVera"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        font_path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
        pdfmetrics.registerFont(TTFont(font_name, font_path))
    output = io.BytesIO()
    document = canvas.Canvas(
        output,
        pagesize=(612, 792),
        invariant=1,
        pageCompression=0,
    )
    for page_start in range(0, len(lines), 58):
        text = document.beginText(50, 760)
        text.setFont(font_name, 10)
        text.setLeading(12)
        for line in lines[page_start : page_start + 58]:
            text.textLine(line)
        document.drawText(text)
        document.showPage()
    document.save()
    return output.getvalue()
