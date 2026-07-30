import type {DiscoveredJob, ScreeningLane} from "./types";

interface DiscoveryLaneProps {
  jobs: DiscoveredJob[];
  ingesting: boolean;
  onIngest: () => Promise<void>;
}

const screeningLanes: {lane: ScreeningLane; label: string}[] = [
  {lane: "eligible", label: "Eligible"},
  {lane: "stretch", label: "Stretch"},
  {lane: "maybe", label: "Maybe"},
  {lane: "rejected", label: "Rejected"},
];

export function DiscoveryLane({jobs, ingesting, onIngest}: DiscoveryLaneProps) {
  return (
    <section className="discovery-lane" aria-labelledby="discovered-heading">
      <div className="lane-heading">
        <div>
          <p className="eyebrow">Opportunity pipeline</p>
          <h2 id="discovered-heading">Screened opportunities</h2>
          <p>Normalized role snapshots grouped by eligibility before scoring.</p>
        </div>
        <button
          className="ingest-button"
          type="button"
          disabled={ingesting}
          onClick={() => void onIngest()}
        >
          {ingesting ? "Ingesting…" : "Ingest configured sources"}
        </button>
      </div>

      {jobs.length === 0 ? (
        <p className="empty-lane">No roles discovered yet.</p>
      ) : (
        <div className="screening-lanes">
          {screeningLanes.map(({lane, label}) => {
            const laneJobs = jobs.filter((job) => job.screening.lane === lane);
            return (
              <section
                className={`screening-lane screening-lane-${lane}`}
                aria-labelledby={`screening-${lane}-heading`}
                key={lane}
              >
                <div className="screening-lane-heading">
                  <h3 id={`screening-${lane}-heading`}>{label}</h3>
                  <span>{laneJobs.length}</span>
                </div>
                {laneJobs.length === 0 ? (
                  <p className="empty-screening-lane">No roles in this lane.</p>
                ) : (
                  <div className="job-list">
                    {laneJobs.map((job) => (
                      <article className="job-card" key={job.id}>
                        <div className="job-card-heading">
                          <div>
                            <p className="job-company">
                              {job.company} · {job.location}
                            </p>
                            <h4>{job.title}</h4>
                          </div>
                          <a
                            href={job.preferred_apply_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Apply via preferred source
                          </a>
                        </div>
                        <div className="screening-reasons">
                          <h5>Why {label.toLowerCase()}</h5>
                          <ul>
                            {job.screening.reasons.map((reason) => (
                              <li key={reason}>{reason}</li>
                            ))}
                          </ul>
                        </div>
                        <p className="job-description">{job.description_text}</p>
                        {job.detected_requirements.length > 0 && (
                          <div className="job-requirements">
                            <h5>Detected requirements</h5>
                            <ul>
                              {job.detected_requirements.map((requirement) => (
                                <li key={requirement}>{requirement}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        <p className="job-meta">
                          <span>
                            Sources:{" "}
                            {[
                              ...new Set(
                                job.snapshots.map((snapshot) => snapshot.source_platform),
                              ),
                            ].join(", ")}
                          </span>
                          {" · "}
                          latest snapshot{" "}
                          {new Date(job.fetched_at).toLocaleString()}
                        </p>
                        <details className="snapshot-history">
                          <summary>Snapshot history ({job.snapshots.length})</summary>
                          <div className="snapshot-list">
                            {job.snapshots.map((snapshot) => (
                              <article className="snapshot-card" key={snapshot.id}>
                                <div className="snapshot-heading">
                                  <a
                                    href={snapshot.canonical_url}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    {snapshot.source_platform} snapshot
                                  </a>
                                  <time dateTime={snapshot.fetched_at}>
                                    {new Date(snapshot.fetched_at).toLocaleString()}
                                  </time>
                                </div>
                                <p>
                                  {snapshot.company} · {snapshot.location}
                                </p>
                                <p className="snapshot-title">{snapshot.title}</p>
                                <p>{snapshot.description_text}</p>
                                <details>
                                  <summary>Raw posting</summary>
                                  <pre>{JSON.stringify(snapshot.raw_posting, null, 2)}</pre>
                                </details>
                              </article>
                            ))}
                          </div>
                        </details>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}
    </section>
  );
}
