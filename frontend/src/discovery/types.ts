export interface DiscoveredJob {
  id: number;
  source_url: string;
  fetched_at: string;
  company: string;
  title: string;
  location: string;
  description_text: string;
  detected_requirements: string[];
  source_platform: string;
  ats_posting_id: string | null;
  canonical_url: string;
  preferred_apply_url: string;
  snapshots: ContributingSnapshot[];
  screening: {
    lane: ScreeningLane;
    reasons: string[];
  };
}

export interface ContributingSnapshot {
  id: number;
  source_url: string;
  fetched_at: string;
  company: string;
  title: string;
  location: string;
  description_text: string;
  detected_requirements: string[];
  source_platform: string;
  ats_posting_id: string | null;
  canonical_url: string;
  raw_posting: Record<string, unknown>;
}

export type ScreeningLane = "eligible" | "stretch" | "maybe" | "rejected";

export interface IngestionResult {
  discovered: number;
  sources: SourceIngestionDiagnostic[];
}

export interface ScoreDimension {
  value: number;
  explanation: string;
}

export interface OpportunityScore {
  total: number;
  weights: {
    eligibility: number;
    role_fit: number;
    skill_overlap: number;
    company_quality: number;
    application_effort: number;
  };
  eligibility: ScoreDimension;
  role_fit: ScoreDimension;
  skill_overlap: ScoreDimension;
  company_quality: ScoreDimension;
  application_effort: ScoreDimension;
}

export interface ScoredOpportunity extends DiscoveredJob {
  score: OpportunityScore;
}

export interface QueueCriteria {
  minimum_score: number;
  include_maybe: boolean;
}

export interface ExpansionLever {
  id: "include_maybe" | "minimum_score";
  label: string;
  description: string;
  criteria: QueueCriteria;
}

export interface CandidateQueue {
  target: {
    minimum: number;
    maximum: number;
  };
  criteria: QueueCriteria;
  candidates: ScoredOpportunity[];
  not_queued: ScoredOpportunity[];
  shortfall: number;
  summary: string;
  expansion_levers: ExpansionLever[];
}

export interface SourceIngestionDiagnostic {
  platform: string;
  identifier: string;
  status: "succeeded" | "failed";
  discovered: number;
  error: string | null;
}
