export interface DiscoveredJob {
  id: number;
  source_url: string;
  fetched_at: string;
  company: string;
  title: string;
  location: string;
  description_text: string;
  detected_requirements: string[];
  source_platform: "greenhouse";
  ats_posting_id: string | null;
  canonical_url: string;
}

export interface IngestionResult {
  discovered: number;
}
