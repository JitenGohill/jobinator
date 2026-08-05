export interface ApplicationPacketPreview {
  id: number;
  profile_version: number;
  opportunity_id: number;
  job_snapshot: {id: number};
  tailored_cv_draft: string;
  cover_letter: string | null;
  risk_flags: {category: string; message: string}[];
}

export type DocumentType = "cv" | "cover_letter";

export interface ExportedDocument {
  document_type: DocumentType;
  version: number;
  preview_markdown: string;
  markdown_url: string;
  pdf_url: string;
}

export interface ExportBundle {
  packet_id: number;
  profile_version: number;
  job_snapshot_id: number;
  documents: ExportedDocument[];
}
