import type {DiscoveredJob, IngestionResult} from "./types";

const discoveryPath = "/api/discovery/jobs";
const ingestionPath = "/api/discovery/ingest";

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as {detail?: string};
    return body.detail ?? `Request failed with status ${response.status}.`;
  } catch {
    return `Request failed with status ${response.status}.`;
  }
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
