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
  source_platform: string;
}

export type ScreeningLane = "eligible" | "stretch" | "maybe" | "rejected";

export interface IngestionResult {
  discovered: number;
}
