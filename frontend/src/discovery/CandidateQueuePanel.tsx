import type {
  CandidateQueue,
  OpportunityScore,
  QueueCriteria,
  ScoredOpportunity,
} from "./types";

interface CandidateQueuePanelProps {
  queue: CandidateQueue;
  loading: boolean;
  onExpand: (criteria: QueueCriteria) => Promise<void>;
}

type DimensionName = keyof OpportunityScore["weights"];

const dimensions: {name: DimensionName; label: string}[] = [
  {name: "eligibility", label: "Eligibility"},
  {name: "role_fit", label: "Role fit"},
  {name: "skill_overlap", label: "Skill overlap"},
  {name: "company_quality", label: "Company quality"},
  {name: "application_effort", label: "Application effort"},
];

const percentage = (weight: number) => `${Math.round(weight * 100)}%`;

function ScoreBreakdown({score}: {score: OpportunityScore}) {
  return (
    <dl className="score-breakdown">
      {dimensions.map(({name, label}) => (
        <div className="score-dimension" key={name}>
          <dt>
            {label} · {percentage(score.weights[name])}
          </dt>
          <dd>
            <strong>{score[name].value}</strong>
            <span>{score[name].explanation}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

function CandidateCard({
  candidate,
  position,
}: {
  candidate: ScoredOpportunity;
  position: number;
}) {
  return (
    <article className="candidate-card">
      <div className="candidate-heading">
        <div className="candidate-position" aria-label={`Queue position ${position}`}>
          {position}
        </div>
        <div>
          <p className="job-company">
            {candidate.company} · {candidate.location}
          </p>
          <h3>{candidate.title}</h3>
          {candidate.screening.lane === "stretch" && (
            <span className="stretch-badge">Stretch</span>
          )}
        </div>
        <div className="total-score">
          <strong>{candidate.score.total} / 100</strong>
          <span>Total score</span>
        </div>
      </div>
      <ScoreBreakdown score={candidate.score} />
      <a
        className="candidate-apply-link"
        href={candidate.preferred_apply_url}
        target="_blank"
        rel="noreferrer"
      >
        Apply via preferred source
      </a>
    </article>
  );
}

export function CandidateQueuePanel({
  queue,
  loading,
  onExpand,
}: CandidateQueuePanelProps) {
  return (
    <section className="candidate-queue" aria-labelledby="candidate-queue-heading">
      <div className="queue-heading">
        <div>
          <p className="eyebrow">Quality-first shortlist</p>
          <h2 id="candidate-queue-heading">Daily candidate queue</h2>
          <p>
            Ranked against the latest job snapshots and your canonical profile.
          </p>
        </div>
        <div className="queue-criteria" aria-label="Current queue criteria">
          <span>
            Target: {queue.target.minimum}–{queue.target.maximum}
          </span>
          <span>Quality threshold: {queue.criteria.minimum_score}</span>
          <span>
            Manual review: {queue.criteria.include_maybe ? "included" : "excluded"}
          </span>
        </div>
      </div>

      <p
        className={queue.shortfall ? "queue-summary queue-shortfall" : "queue-summary"}
        role="status"
      >
        {queue.summary}
      </p>

      {queue.expansion_levers.length > 0 && (
        <section className="expansion-levers" aria-labelledby="expansion-heading">
          <div>
            <h3 id="expansion-heading">Expand this queue</h3>
            <p>These controls never change hard eligibility rules.</p>
          </div>
          <div className="expansion-actions">
            {queue.expansion_levers.map((lever) => (
              <button
                type="button"
                key={lever.id}
                disabled={loading}
                title={lever.description}
                onClick={() => void onExpand(lever.criteria)}
              >
                {lever.label}
              </button>
            ))}
          </div>
        </section>
      )}

      {queue.candidates.length === 0 ? (
        <p className="empty-lane">No opportunities meet the current queue criteria.</p>
      ) : (
        <div className="candidate-list">
          {queue.candidates.map((candidate, index) => (
            <CandidateCard
              candidate={candidate}
              position={index + 1}
              key={candidate.id}
            />
          ))}
        </div>
      )}

      {queue.not_queued.length > 0 && (
        <details className="not-queued">
          <summary>Scored but not queued ({queue.not_queued.length})</summary>
          <div className="not-queued-list">
            {queue.not_queued.map((candidate) => (
              <article key={candidate.id}>
                <div className="not-queued-heading">
                  <h3>{candidate.title}</h3>
                  <span>
                    {candidate.score.total} / 100 · {candidate.screening.lane}
                  </span>
                </div>
                <ScoreBreakdown score={candidate.score} />
              </article>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}
