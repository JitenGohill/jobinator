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
  source_platform: string;
  original_score: OpportunityScore | null;
  packet_id: number | null;
  applied_at: string | null;
  company_type: CompanyType | null;
  document_versions: SubmittedDocumentVersion[];
  outcomes: OutcomeEvent[];
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
  outcome_type?: OutcomeType;
  occurred_at?: string;
  company_type?: CompanyType;
  document_versions?: SubmittedDocumentVersion[];
}

export type OutcomeType = "response" | "recruiter_screen" | "interview" | "rejection" | "offer";
export type CompanyType =
  | "product"
  | "startup"
  | "enterprise"
  | "agency"
  | "consultancy"
  | "nonprofit"
  | "government"
  | "other";

export interface SubmittedDocumentVersion {
  document_type: DocumentType;
  version: number;
}

export interface OutcomeEvent {
  outcome_type: OutcomeType;
  note: string;
  occurred_at: string;
}

export interface AnalyticsRate {
  numerator: number;
  denominator: number;
  rate: number | null;
}

export interface AnalyticsGroupRate {
  group: string;
  applications: number;
  responses: number;
  response_rate: number;
}

export interface ApplicationAnalytics {
  packets_prepared: number;
  applications_submitted: number;
  applications_per_day: {date: string; count: number}[];
  review_rejection_rate: AnalyticsRate;
  source_quality: AnalyticsGroupRate[];
  score_distribution: {label: string; minimum: number; maximum: number; count: number}[];
  response_rate_by_role: AnalyticsGroupRate[];
  response_rate_by_source: AnalyticsGroupRate[];
  response_rate_by_company_type: AnalyticsGroupRate[];
  common_reject_reasons: {reason: string; count: number}[];
  definitions: {
    review_rejection_rate: string;
    source_quality: string;
    response_rate: string;
  };
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
