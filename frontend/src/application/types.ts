import type {OpportunityScore} from "../discovery/types";

export interface ApplicationPacketPreview {
  id: number;
  profile_version: number;
  opportunity_id: number;
  score: OpportunityScore;
  job_snapshot: {id: number; company?: string; title?: string};
  tailored_cv_draft: string;
  matched_profile_context: {
    skills: string[];
    projects: string[];
    work_experience: string[];
  };
  missing_requirements: string[];
  cover_letter: string | null;
  risk_flags: {category: string; message: string}[];
  direct_apply_link: string;
  estimated_application_effort: "low" | "moderate" | "high";
  screening_answers: {
    question: string;
    draft: string;
    review_required: true;
  }[];
}

export type WorkflowStage =
  | "discovered"
  | "shortlisted"
  | "packet_ready"
  | "reviewed"
  | "applied"
  | "rejected_skipped"
  | "follow_up"
  | "outcome";

export interface WorkflowItem {
  opportunity_id: number;
  stage: WorkflowStage;
  disposition: "rejected" | "skipped" | null;
  skip_reason: string | null;
  outcome: string | null;
  opportunity: {
    company: string;
    title: string;
    location: string;
    direct_apply_link: string;
  };
  packet: ApplicationPacketPreview | null;
  history: {
    from_stage: WorkflowStage | null;
    to_stage: WorkflowStage;
    note: string | null;
    occurred_at: string;
  }[];
}

export interface WorkflowBoard {
  items: WorkflowItem[];
}

export interface WorkflowTransitionRequest {
  target_stage: WorkflowStage;
  skip_reason?: string;
  submitted_externally?: boolean;
  outcome?: string;
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
