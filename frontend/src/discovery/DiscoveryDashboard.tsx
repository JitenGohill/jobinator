import {useEffect, useState} from "react";

import {CandidateQueuePanel} from "./CandidateQueuePanel";
import {DiscoveryLinkIntake} from "./DiscoveryLinkIntake";
import {DiscoveryLane} from "./DiscoveryLane";
import {
  addDiscoveryLinks,
  ingestConfiguredSources,
  loadCandidateQueue,
  loadDiscoveredJobs,
  loadDiscoveryLinkSources,
  loadDiscoveryLinks,
} from "./discoveryClient";
import type {
  CandidateQueue,
  DiscoveryLink,
  DiscoveryLinkSource,
  DiscoveryLinkSubmission,
  DiscoveredJob,
  IngestionResult,
  QueueCriteria,
} from "./types";

interface DiscoveryDashboardProps {
  profileVersion?: number | null;
}

const defaultQueueCriteria: QueueCriteria = {
  minimum_score: 60,
  include_maybe: false,
};

export function DiscoveryDashboard({profileVersion}: DiscoveryDashboardProps) {
  const [jobs, setJobs] = useState<DiscoveredJob[]>([]);
  const [ingesting, setIngesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ingestionResult, setIngestionResult] = useState<IngestionResult | null>(null);
  const [queue, setQueue] = useState<CandidateQueue | null>(null);
  const [queueCriteria, setQueueCriteria] =
    useState<QueueCriteria>(defaultQueueCriteria);
  const [queueMessage, setQueueMessage] = useState<string | null>(null);
  const [queueLoading, setQueueLoading] = useState(false);
  const [discoveryLinks, setDiscoveryLinks] = useState<DiscoveryLink[]>([]);
  const [discoveryLinkSources, setDiscoveryLinkSources] = useState<
    DiscoveryLinkSource[]
  >([]);
  const [submittingLinks, setSubmittingLinks] = useState(false);

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
    void loadCandidateQueue(queueCriteria)
      .then((candidateQueue) => {
        if (active) {
          setQueue(candidateQueue);
          setQueueMessage(null);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setQueue(null);
          setQueueMessage(
            reason instanceof Error ? reason.message : "Could not generate the candidate queue.",
          );
        }
      });
    void loadDiscoveryLinks()
      .then((links) => {
        if (active) {
          setDiscoveryLinks(links);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Could not load discovery links.");
        }
      });
    void loadDiscoveryLinkSources()
      .then((sources) => {
        if (active) {
          setDiscoveryLinkSources(sources);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Could not load discovery-link sources.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [profileVersion]);

  const refreshQueue = async (criteria: QueueCriteria) => {
    setQueueLoading(true);
    setQueueMessage(null);
    setQueueCriteria(criteria);
    try {
      setQueue(await loadCandidateQueue(criteria));
    } catch (reason) {
      setQueue(null);
      setQueueMessage(
        reason instanceof Error ? reason.message : "Could not generate the candidate queue.",
      );
    } finally {
      setQueueLoading(false);
    }
  };

  const ingest = async () => {
    setIngesting(true);
    setError(null);
    setIngestionResult(null);
    try {
      setIngestionResult(await ingestConfiguredSources());
      setJobs(await loadDiscoveredJobs());
      await refreshQueue(queueCriteria);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not ingest configured sources.");
    } finally {
      setIngesting(false);
    }
  };

  const submitDiscoveryLinks = async (links: DiscoveryLinkSubmission[]) => {
    setSubmittingLinks(true);
    setError(null);
    try {
      const result = await addDiscoveryLinks(links);
      setDiscoveryLinks((current) => [...result.links, ...current]);
      setJobs(await loadDiscoveredJobs());
      await refreshQueue(queueCriteria);
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not add discovery links.");
      return false;
    } finally {
      setSubmittingLinks(false);
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
      <DiscoveryLinkIntake
        links={discoveryLinks}
        sourceOptions={discoveryLinkSources}
        submitting={submittingLinks}
        onSubmit={submitDiscoveryLinks}
      />
      {queueMessage && (
        <section className="queue-unavailable" aria-label="Candidate queue unavailable">
          <h2>Daily candidate queue</h2>
          <p>{queueMessage}</p>
        </section>
      )}
      {queue && (
        <CandidateQueuePanel
          queue={queue}
          loading={queueLoading}
          onExpand={refreshQueue}
        />
      )}
      <DiscoveryLane jobs={jobs} ingesting={ingesting} onIngest={ingest} />
    </>
  );
}
