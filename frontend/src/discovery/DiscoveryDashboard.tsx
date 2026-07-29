import {useEffect, useState} from "react";

import {DiscoveryLane} from "./DiscoveryLane";
import {ingestConfiguredSources, loadDiscoveredJobs} from "./discoveryClient";
import type {DiscoveredJob} from "./types";

export function DiscoveryDashboard() {
  const [jobs, setJobs] = useState<DiscoveredJob[]>([]);
  const [ingesting, setIngesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    try {
      await ingestConfiguredSources();
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
      <DiscoveryLane jobs={jobs} ingesting={ingesting} onIngest={ingest} />
    </>
  );
}
