import {useCallback, useEffect, useState} from "react";

import {decideStrategyProposal, loadStrategyAdvice} from "./applicationClient";
import type {
  GapFinding,
  ProposalDecision,
  RankingDimension,
  RankingProposal,
  StrategyAdvice,
} from "./types";

export function StrategyAdvicePanel() {
  const [advice, setAdvice] = useState<StrategyAdvice | null>(null);
  const [workingId, setWorkingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setAdvice(await loadStrategyAdvice());
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load strategy advice.");
    }
  }, []);

  useEffect(() => {
    void load();
    window.addEventListener("application-workflow-updated", load);
    return () => window.removeEventListener("application-workflow-updated", load);
  }, [load]);

  const decide = async (proposal: RankingProposal, decision: ProposalDecision) => {
    setWorkingId(proposal.id);
    setError(null);
    try {
      const updated = await decideStrategyProposal(proposal.id, decision);
      setAdvice((current) => current && ({
        ...current,
        ranking_proposals: current.ranking_proposals.map(
          (item) => item.id === updated.id ? updated : item,
        ),
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not record the proposal decision.");
    } finally {
      setWorkingId(null);
    }
  };

  return (
    <section className="strategy-advice" aria-labelledby="strategy-advice-heading">
      <div className="workflow-heading">
        <div>
          <p className="eyebrow">Review before changing behavior</p>
          <h1 id="strategy-advice-heading">Search strategy advice</h1>
        </div>
        <p>Recommendations use current opportunity and outcome evidence. Nothing is applied silently.</p>
      </div>
      {error && <p className="error-message" role="alert">{error}</p>}
      {advice && (
        <div className="strategy-grid">
          <section aria-labelledby="profile-gaps-heading">
            <h2 id="profile-gaps-heading">Recurring profile gaps</h2>
            {advice.gap_findings.length === 0 && <p>No recurring high-quality gaps yet.</p>}
            {advice.gap_findings.map((finding) => <GapCard key={finding.requirement} finding={finding} />)}
          </section>
          <section aria-labelledby="ranking-proposals-heading">
            <h2 id="ranking-proposals-heading">Ranking proposals</h2>
            {advice.ranking_proposals.length === 0 && <p>No outcome-backed proposal yet.</p>}
            {advice.ranking_proposals.map((proposal) => (
              <article className="strategy-card" key={proposal.id}>
                <div className="proposal-heading">
                  <h3>{titleCase(proposal.dimension)} weight: {proposal.direction}</h3>
                  <span className={`proposal-status ${proposal.status}`}>{titleCase(proposal.status)}</span>
                </div>
                <p>{proposal.rationale}</p>
                <div className="proposal-weight-changes">
                  {changedDimensions(proposal).map((dimension) => (
                    <p key={dimension}>
                      Proposed {dimension.replaceAll("_", " ")} weight: {formatWeight(
                        proposal.current_weights[dimension],
                      )} → {formatWeight(proposal.proposed_weights[dimension])}
                    </p>
                  ))}
                </div>
                <ul>
                  {proposal.evidence.map((entry) => (
                    <li key={`${entry.opportunity_id}-${entry.outcome}`}>
                      {entry.company} · {entry.title} · {entry.outcome} · {proposal.dimension.replaceAll("_", " ")} {entry.dimension_value}
                    </li>
                  ))}
                </ul>
                {proposal.status === "pending" && (
                  <div className="proposal-actions">
                    <button
                      type="button"
                      disabled={workingId === proposal.id}
                      onClick={() => void decide(proposal, "accepted")}
                    >
                      Accept ranking proposal
                    </button>
                    <button
                      type="button"
                      disabled={workingId === proposal.id}
                      onClick={() => void decide(proposal, "rejected")}
                    >
                      Reject ranking proposal
                    </button>
                  </div>
                )}
              </article>
            ))}
          </section>
        </div>
      )}
    </section>
  );
}

function GapCard({finding}: {finding: GapFinding}) {
  return (
    <article className="strategy-card" aria-label={`${finding.requirement} gap`}>
      <h3>{finding.requirement}</h3>
      <p>Seen in {finding.occurrences} high-scoring roles</p>
      <p>Consider: {finding.priority_options.map(titleCase).join(" · ")}</p>
      <ul>
        {finding.opportunities.map((opportunity) => {
          const matched = [
            ...opportunity.matched_skills,
            ...opportunity.matched_projects,
            ...opportunity.matched_work_experience,
          ];
          return (
            <li key={opportunity.opportunity_id}>
              <strong>{opportunity.company} · {opportunity.title} · {opportunity.score}/100</strong>
              <span>Matched evidence: {matched.length ? matched.join("; ") : "none recorded"}</span>
            </li>
          );
        })}
      </ul>
    </article>
  );
}

function titleCase(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function formatWeight(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function changedDimensions(proposal: RankingProposal): RankingDimension[] {
  return (Object.keys(proposal.current_weights) as RankingDimension[]).filter(
    (dimension) => proposal.current_weights[dimension] !== proposal.proposed_weights[dimension],
  );
}
