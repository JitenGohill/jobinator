import type {
  CandidateQueue,
  DiscoveredJob,
  IngestionResult,
  QueueCriteria,
} from "./types";

const discoveryPath = "/api/discovery/jobs";
const ingestionPath = "/api/discovery/ingest";
const queuePath = "/api/discovery/queue";

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as {detail?: string};
    return body.detail ?? `Request failed with status ${response.status}.`;
  } catch {
    return `Request failed with status ${response.status}.`;
  }
}

function isCandidateQueue(value: unknown): value is CandidateQueue {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const queue = value as Partial<CandidateQueue>;
  return (
    typeof queue.target?.minimum === "number" &&
    typeof queue.target.maximum === "number" &&
    typeof queue.criteria?.minimum_score === "number" &&
    typeof queue.criteria.include_maybe === "boolean" &&
    Array.isArray(queue.candidates) &&
    Array.isArray(queue.not_queued) &&
    Array.isArray(queue.expansion_levers) &&
    typeof queue.shortfall === "number" &&
    typeof queue.summary === "string"
  );
}

export async function loadDiscoveredJobs(): Promise<DiscoveredJob[]> {
  const response = await fetch(discoveryPath);
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as DiscoveredJob[];
}

export async function ingestConfiguredSources(): Promise<IngestionResult> {
  const response = await fetch(ingestionPath, {method: "POST"});
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as IngestionResult;
}

export async function loadCandidateQueue(
  criteria: QueueCriteria,
): Promise<CandidateQueue> {
  const query = new URLSearchParams({
    minimum_score: String(criteria.minimum_score),
    include_maybe: String(criteria.include_maybe),
  });
  const response = await fetch(`${queuePath}?${query.toString()}`);
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  const body: unknown = await response.json();
  if (!isCandidateQueue(body)) {
    throw new Error("The candidate queue response was invalid.");
  }
  return body;
}
