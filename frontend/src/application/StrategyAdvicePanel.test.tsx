import {cleanup, render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach, expect, test, vi} from "vitest";

import {StrategyAdvicePanel} from "./StrategyAdvicePanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const pendingAdvice = {
  gap_findings: [{
    requirement: "Go",
    occurrences: 2,
    priority_options: ["learning", "portfolio", "profile_presentation"],
    opportunities: [{
      opportunity_id: 1,
      company: "Alpha Systems",
      title: "Junior Backend Engineer",
      score: 90,
      source_platform: "company",
      matched_skills: ["Python"],
      matched_projects: ["Queue Lens"],
      matched_work_experience: [],
    }],
  }],
  ranking_proposals: [{
    id: 4,
    status: "pending",
    dimension: "company_quality",
    direction: "increase",
    rationale: "Interview outcomes scored higher than rejection outcomes for company quality.",
    current_weights: {eligibility: 0.3, company_quality: 0.15},
    proposed_weights: {eligibility: 0.25, company_quality: 0.2},
    evidence: [
      {opportunity_id: 1, company: "Alpha Systems", title: "Junior Backend Engineer", outcome: "interview", dimension_value: 100},
      {opportunity_id: 2, company: "Beta Cloud", title: "Junior Backend Engineer", outcome: "rejection", dimension_value: 85},
    ],
  }],
};

test("user can judge gap evidence and explicitly accept a ranking proposal", async () => {
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (input === "/api/strategy-advice") {
      return new Response(JSON.stringify(pendingAdvice), {status: 200});
    }
    if (input === "/api/strategy-proposals/4/decision" && init?.method === "POST") {
      return new Response(JSON.stringify({
        ...pendingAdvice.ranking_proposals[0],
        status: "accepted",
      }), {status: 200});
    }
    return new Response(JSON.stringify({detail: "not found"}), {status: 404});
  });
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();

  render(<StrategyAdvicePanel />);

  const gap = await screen.findByRole("article", {name: "Go gap"});
  expect(within(gap).getByText("Seen in 2 high-scoring roles")).toBeInTheDocument();
  expect(within(gap).getByText(/Alpha Systems · Junior Backend Engineer · 90/)).toBeInTheDocument();
  expect(within(gap).getByText(/Matched evidence: Python; Queue Lens/)).toBeInTheDocument();
  expect(within(gap).getByText(/Learning · Portfolio · Profile presentation/)).toBeInTheDocument();

  expect(screen.getByText(/Interview outcomes scored higher/)).toBeInTheDocument();
  expect(screen.getByText("Proposed company quality weight: 15% → 20%")).toBeInTheDocument();
  expect(screen.getByText("Proposed eligibility weight: 30% → 25%")).toBeInTheDocument();
  expect(screen.getByText(/Alpha Systems · Junior Backend Engineer · interview · company quality 100/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", {name: "Accept ranking proposal"}));

  await waitFor(() => expect(screen.getByText("Accepted")).toBeInTheDocument());
  expect(fetch).toHaveBeenCalledWith("/api/strategy-proposals/4/decision", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({decision: "accepted"}),
  });
});

test("dismissed proposals remain visible as recorded decisions without action controls", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    gap_findings: [],
    ranking_proposals: [{...pendingAdvice.ranking_proposals[0], status: "rejected"}],
  }), {status: 200})));

  render(<StrategyAdvicePanel />);

  expect(await screen.findByText("Rejected")).toBeInTheDocument();
  expect(screen.queryByRole("button", {name: "Accept ranking proposal"})).not.toBeInTheDocument();
  expect(screen.queryByRole("button", {name: "Reject ranking proposal"})).not.toBeInTheDocument();
});
