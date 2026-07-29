import type {DiscoveredJob} from "./types";

interface DiscoveryLaneProps {
  jobs: DiscoveredJob[];
  ingesting: boolean;
  onIngest: () => Promise<void>;
}

export function DiscoveryLane({jobs, ingesting, onIngest}: DiscoveryLaneProps) {
  return (
    <section className="discovery-lane" aria-labelledby="discovered-heading">
      <div className="lane-heading">
        <div>
          <p className="eyebrow">Opportunity pipeline</p>
          <h2 id="discovered-heading">Discovered</h2>
          <p>Immutable role snapshots captured from your configured job sources.</p>
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
        <div className="job-list">
          {jobs.map((job) => (
            <article className="job-card" key={job.id}>
              <div className="job-card-heading">
                <div>
                  <p className="job-company">
                    {job.company} · {job.location}
                  </p>
                  <h3>{job.title}</h3>
                </div>
                <a href={job.canonical_url} target="_blank" rel="noreferrer">
                  View source
                </a>
              </div>
              <p className="job-description">{job.description_text}</p>
              {job.detected_requirements.length > 0 && (
                <div className="job-requirements">
                  <h4>Detected requirements</h4>
                  <ul>
                    {job.detected_requirements.map((requirement) => (
                      <li key={requirement}>{requirement}</li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="job-meta">
                {job.source_platform} · fetched {new Date(job.fetched_at).toLocaleString()}
                {job.ats_posting_id ? ` · ATS ID ${job.ats_posting_id}` : ""}
              </p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
