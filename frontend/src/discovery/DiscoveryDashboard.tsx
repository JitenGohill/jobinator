import {useEffect, useState} from "react";

import {DiscoveryLane} from "./DiscoveryLane";
import {ingestConfiguredSources, loadDiscoveredJobs} from "./discoveryClient";
import type {DiscoveredJob, IngestionResult} from "./types";

export function DiscoveryDashboard() {
  const [jobs, setJobs] = useState<DiscoveredJob[]>([]);
  const [ingesting, setIngesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ingestionResult, setIngestionResult] = useState<IngestionResult | null>(null);

  useEffect(() => {
    let active = true;
    void loadDiscoveredJobs()
      .then((discoveredJobs) => {
        if (active) {
          setJobs(discoveredJobs);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Could not load discovered roles.");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const ingest = async () => {
    setIngesting(true);
    setError(null);
    setIngestionResult(null);
    try {
      setIngestionResult(await ingestConfiguredSources());
      setJobs(await loadDiscoveredJobs());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not ingest configured sources.");
    } finally {
      setIngesting(false);
    }
  };

  return (
    <>
      {error && (
        <p className="error-message discovery-error" role="alert">
          {error}
        </p>
      )}
      {ingestionResult && (
        <section className="ingestion-result" aria-label="Source ingestion result">
          <p role="status">
            {ingestionResult.discovered}{" "}
            {ingestionResult.discovered === 1 ? "snapshot" : "snapshots"} discovered
          </p>
          <ul>
            {ingestionResult.sources.map((source) => (
              <li key={`${source.platform}:${source.identifier}`}>
                {source.platform} ({source.identifier}):{" "}
                {source.status === "succeeded"
                  ? `discovered ${source.discovered}`
                  : source.error}
              </li>
            ))}
          </ul>
        </section>
      )}
      <DiscoveryLane jobs={jobs} ingesting={ingesting} onIngest={ingest} />
    </>
  );
}
