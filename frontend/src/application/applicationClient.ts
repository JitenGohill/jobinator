import type {
  ApplicationPacketPreview,
  ApplicationAnalytics,
  ExportBundle,
  WorkflowBoard,
  WorkflowItem,
  WorkflowTransitionRequest,
  ProposalDecision,
  RankingProposal,
  StrategyAdvice,
} from "./types";

async function requireJson<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T;
  }
  try {
    const body = (await response.json()) as {detail?: string};
    throw new Error(body.detail ?? `Request failed with status ${response.status}.`);
  } catch (reason) {
    if (reason instanceof Error && !reason.message.startsWith("Unexpected token")) {
      throw reason;
    }
    throw new Error(`Request failed with status ${response.status}.`);
  }
}

export async function prepareApplicationPacket(
  opportunityId: number,
  screeningQuestions: string[] = [],
): Promise<ApplicationPacketPreview> {
  const response = await fetch(`/api/application-packets/${opportunityId}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({cover_letter_requested: false, screening_questions: screeningQuestions}),
  });
  return requireJson<ApplicationPacketPreview>(response);
}

export async function exportApplicationPacket(packetId: number): Promise<ExportBundle> {
  const response = await fetch(`/api/application-packets/${packetId}/exports`, {
    method: "POST",
  });
  return requireJson<ExportBundle>(response);
}

export async function loadApplicationWorkflow(): Promise<WorkflowBoard> {
  const board = await requireJson<WorkflowBoard>(await fetch("/api/application-workflow"));
  if (!Array.isArray(board.items)) {
    throw new Error("The application workflow response was invalid.");
  }
  return board;
}

export async function loadApplicationAnalytics(): Promise<ApplicationAnalytics> {
  const analytics = await requireJson<ApplicationAnalytics>(
    await fetch("/api/application-analytics"),
  );
  if (
    typeof analytics.packets_prepared !== "number"
    || typeof analytics.applications_submitted !== "number"
    || !analytics.review_rejection_rate
    || !Array.isArray(analytics.applications_per_day)
  ) {
    throw new Error("The application analytics response was invalid.");
  }
  return analytics;
}

export async function loadStrategyAdvice(): Promise<StrategyAdvice> {
  const advice = await requireJson<StrategyAdvice>(await fetch("/api/strategy-advice"));
  if (!Array.isArray(advice.gap_findings) || !Array.isArray(advice.ranking_proposals)) {
    throw new Error("The strategy advice response was invalid.");
  }
  return advice;
}

export async function decideStrategyProposal(
  proposalId: number,
  decision: ProposalDecision,
): Promise<RankingProposal> {
  return requireJson<RankingProposal>(await fetch(`/api/strategy-proposals/${proposalId}/decision`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({decision}),
  }));
}

export async function transitionApplicationWorkflow(
  opportunityId: number,
  request: WorkflowTransitionRequest,
): Promise<WorkflowItem> {
  const response = await fetch(`/api/application-workflow/${opportunityId}/transitions`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(request),
  });
  return requireJson<WorkflowItem>(response);
}
