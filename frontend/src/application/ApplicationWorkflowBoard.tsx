import {useCallback, useEffect, useState} from "react";

import {
  loadApplicationWorkflow,
  prepareApplicationPacket,
  transitionApplicationWorkflow,
} from "./applicationClient";
import type {
  ApplicationPacketPreview,
  WorkflowItem,
  WorkflowStage,
  WorkflowTransitionRequest,
} from "./types";

const columns: {stage: WorkflowStage; label: string}[] = [
  {stage: "discovered", label: "Discovered"},
  {stage: "shortlisted", label: "Shortlisted"},
  {stage: "packet_ready", label: "Packet ready"},
  {stage: "reviewed", label: "Reviewed"},
  {stage: "applied", label: "Applied"},
  {stage: "rejected_skipped", label: "Rejected / skipped"},
  {stage: "follow_up", label: "Follow-up"},
  {stage: "outcome", label: "Outcome"},
];

export function ApplicationWorkflowBoard({refreshKey}: {refreshKey: number | null}) {
  const [items, setItems] = useState<WorkflowItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setItems((await loadApplicationWorkflow()).items);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load the workflow.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const update = (item: WorkflowItem) => {
    setItems((current) => current.map((existing) =>
      existing.opportunity_id === item.opportunity_id ? item : existing,
    ));
  };

  const transition = async (
    opportunityId: number,
    request: WorkflowTransitionRequest,
  ) => {
    update(await transitionApplicationWorkflow(opportunityId, request));
  };

  const prepare = async (opportunityId: number, screeningQuestions: string[]) => {
    await prepareApplicationPacket(opportunityId, screeningQuestions);
    await load();
  };

  return (
    <section className="workflow" aria-labelledby="workflow-heading">
      <div className="workflow-heading">
        <div>
          <p className="eyebrow">Human-in-the-loop operations</p>
          <h1 id="workflow-heading">Application workflow</h1>
        </div>
        <p>Jobinator organizes review. You remain in control of every submission.</p>
      </div>
      {error && <p className="error-message" role="alert">{error}</p>}
      <div className="workflow-board" aria-busy={loading}>
        {columns.map((column) => {
          const stageItems = items.filter((item) => item.stage === column.stage);
          return (
            <section className="workflow-column" key={column.stage}>
              <h2>{column.label}</h2>
              <span className="workflow-count">{stageItems.length}</span>
              <div className="workflow-cards">
                {stageItems.map((item) => (
                  <WorkflowCard
                    item={item}
                    key={item.opportunity_id}
                    onPrepare={prepare}
                    onTransition={transition}
                  />
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </section>
  );
}

function WorkflowCard({
  item,
  onPrepare,
  onTransition,
}: {
  item: WorkflowItem;
  onPrepare: (opportunityId: number, screeningQuestions: string[]) => Promise<void>;
  onTransition: (
    opportunityId: number,
    request: WorkflowTransitionRequest,
  ) => Promise<void>;
}) {
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [skipReason, setSkipReason] = useState("");
  const [outcome, setOutcome] = useState("");
  const [screeningQuestions, setScreeningQuestions] = useState("");

  const act = async (action: () => Promise<void>) => {
    setWorking(true);
    setError(null);
    try {
      await action();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update the workflow.");
    } finally {
      setWorking(false);
    }
  };

  const transition = (request: WorkflowTransitionRequest) =>
    act(() => onTransition(item.opportunity_id, request));

  return (
    <article className="workflow-card">
      <p className="job-company">{item.opportunity.company}</p>
      <h3>{item.opportunity.title}</h3>
      <p className="workflow-location">{item.opportunity.location}</p>

      {item.stage === "discovered" && (
        <button type="button" disabled={working} onClick={() => void transition({target_stage: "shortlisted"})}>
          Add to shortlist
        </button>
      )}
      {item.stage === "shortlisted" && (
        <div className="workflow-detail-action">
          <label htmlFor={`questions-${item.opportunity_id}`}>
            Screening questions (one per line)
          </label>
          <textarea
            id={`questions-${item.opportunity_id}`}
            value={screeningQuestions}
            onChange={(event) => setScreeningQuestions(event.target.value)}
          />
          <button
            type="button"
            disabled={working}
            onClick={() => void act(() => onPrepare(
              item.opportunity_id,
              screeningQuestions.split("\n").map((question) => question.trim()).filter(Boolean),
            ))}
          >
            Prepare review packet
          </button>
        </div>
      )}
      {item.stage === "packet_ready" && item.packet && (
        <PacketReview packet={item.packet} working={working} onReviewed={() => transition({target_stage: "reviewed"})} />
      )}
      {item.stage === "reviewed" && (
        <div className="manual-handoff">
          <p>Ready for your external submission.</p>
          <a href={item.opportunity.direct_apply_link} target="_blank" rel="noreferrer">
            Open external application
          </a>
          <p>Jobinator never fills or submits the external application.</p>
          <button
            type="button"
            disabled={working}
            onClick={() => void transition({target_stage: "applied", submitted_externally: true})}
          >
            I completed submission externally
          </button>
        </div>
      )}
      {item.stage === "applied" && (
        <button type="button" disabled={working} onClick={() => void transition({target_stage: "follow_up"})}>
          Move to follow-up
        </button>
      )}
      {(item.stage === "applied" || item.stage === "follow_up") && (
        <div className="workflow-detail-action">
          <label htmlFor={`outcome-${item.opportunity_id}`}>Outcome</label>
          <input id={`outcome-${item.opportunity_id}`} value={outcome} onChange={(event) => setOutcome(event.target.value)} />
          <button type="button" disabled={working || !outcome.trim()} onClick={() => void transition({target_stage: "outcome", outcome: outcome.trim()})}>
            Record outcome
          </button>
        </div>
      )}
      {item.stage === "outcome" && item.outcome && <p>{item.outcome}</p>}
      {item.stage === "rejected_skipped" && (
        <p>{item.disposition === "rejected" ? "Rejected by eligibility screening." : `Skipped: ${item.skip_reason}`}</p>
      )}
      {(["discovered", "shortlisted", "packet_ready", "reviewed"] as WorkflowStage[]).includes(item.stage) && (
        <div className="workflow-detail-action">
          <label htmlFor={`skip-${item.opportunity_id}`}>Skip reason</label>
          <input id={`skip-${item.opportunity_id}`} value={skipReason} onChange={(event) => setSkipReason(event.target.value)} />
          <button type="button" disabled={working || !skipReason.trim()} onClick={() => void transition({target_stage: "rejected_skipped", skip_reason: skipReason.trim()})}>
            Skip opportunity
          </button>
        </div>
      )}
      <details className="workflow-history">
        <summary>Transition history</summary>
        <ol>
          {item.history.map((entry, index) => (
            <li key={`${entry.occurred_at}-${index}`}>
              {entry.to_stage.replace("_", " ")}{entry.note ? ` — ${entry.note}` : ""}
            </li>
          ))}
        </ol>
      </details>
      {error && <p className="error-message" role="alert">{error}</p>}
    </article>
  );
}

function PacketReview({
  packet,
  working,
  onReviewed,
}: {
  packet: ApplicationPacketPreview;
  working: boolean;
  onReviewed: () => Promise<void>;
}) {
  return (
    <div className="workflow-packet">
      <p className="workflow-score"><strong>{packet.score.total} / 100</strong></p>
      <p>Estimated effort: {packet.estimated_application_effort}</p>
      <p>Missing requirements: {packet.missing_requirements.join(", ") || "None identified"}</p>
      <ul className="workflow-risks">
        {packet.risk_flags.map((risk) => <li key={`${risk.category}-${risk.message}`}>{risk.message}</li>)}
      </ul>
      <details open>
        <summary>Tailored CV</summary>
        <pre>{packet.tailored_cv_draft.split("\n").map((line, index) => <span key={index}>{line || " "}</span>)}</pre>
      </details>
      {packet.cover_letter && <details><summary>Cover letter</summary><pre>{packet.cover_letter}</pre></details>}
      {packet.screening_answers.map((answer) => (
        <section className="screening-answer" key={answer.question}>
          <h4>{answer.question}</h4>
          <span>Review required</span>
          <p>{answer.draft}</p>
        </section>
      ))}
      <a href={packet.direct_apply_link} target="_blank" rel="noreferrer">Open external application</a>
      <p>Jobinator never fills or submits the external application.</p>
      <button type="button" disabled={working} onClick={() => void onReviewed()}>
        Mark packet reviewed
      </button>
    </div>
  );
}
