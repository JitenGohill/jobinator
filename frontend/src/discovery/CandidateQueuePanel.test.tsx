import {cleanup, render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach, expect, test, vi} from "vitest";

import {CandidateQueuePanel} from "./CandidateQueuePanel";
import type {CandidateQueue} from "./types";

afterEach(cleanup);

const queue: CandidateQueue = {
  target: {minimum: 25, maximum: 30},
  criteria: {minimum_score: 60, include_maybe: false},
  shortfall: 24,
  summary: "1 candidate meets the current criteria; 24 fewer than the 25-candidate target.",
  candidates: [
    {
      id: 1,
      source_url: "https://careers.alpha.example/backend-engineer",
      fetched_at: "2026-07-30T09:00:00Z",
      company: "Alpha Systems",
      title: "Junior Backend Engineer",
      location: "New York, NY",
      description_text: "Build Python and FastAPI services.",
      detected_requirements: ["Python", "FastAPI"],
      source_platform: "company",
      ats_posting_id: "alpha-1",
      canonical_url: "https://careers.alpha.example/backend-engineer",
      preferred_apply_url: "https://careers.alpha.example/backend-engineer",
      snapshots: [],
      screening: {
        lane: "stretch",
        reasons: ["Stretch experience requirement: 3 years."],
      },
      score: {
        total: 91.25,
        weights: {
          eligibility: 0.3,
          role_fit: 0.25,
          skill_overlap: 0.2,
          company_quality: 0.15,
          application_effort: 0.1,
        },
        eligibility: {
          value: 75,
          explanation: "Stretch eligibility: 3 years.",
        },
        role_fit: {
          value: 100,
          explanation: "Strong backend fit with the canonical profile's backend focus.",
        },
        skill_overlap: {
          value: 100,
          explanation: "Matches 2 of 2 detected technologies: FastAPI and Python.",
        },
        company_quality: {
          value: 100,
          explanation: "Official company listing from Alpha Systems.",
        },
        application_effort: {
          value: 100,
          explanation: "Low application effort: official route and 2 detected requirements.",
        },
      },
    },
  ],
  not_queued: [],
  expansion_levers: [
    {
      id: "include_maybe",
      label: "Include manual-review matches",
      description: "Add maybe-lane opportunities without changing hard-reject rules.",
      criteria: {minimum_score: 60, include_maybe: true},
    },
  ],
};

test("daily queue explains scores, labels stretch work, and exposes expansion controls", async () => {
  const expand = vi.fn().mockResolvedValue(undefined);
  const user = userEvent.setup();
  render(<CandidateQueuePanel queue={queue} loading={false} onExpand={expand} />);

  expect(screen.getByRole("heading", {name: "Daily candidate queue"})).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent(
    "1 candidate meets the current criteria; 24 fewer than the 25-candidate target.",
  );
  expect(screen.getByText("Target: 25–30")).toBeInTheDocument();
  expect(screen.getByText("Quality threshold: 60")).toBeInTheDocument();
  expect(screen.getByText("Stretch")).toBeInTheDocument();
  expect(screen.getByText("91.25 / 100")).toBeInTheDocument();
  expect(screen.getByText("Eligibility · 30%")).toBeInTheDocument();
  expect(screen.getByText("Role fit · 25%")).toBeInTheDocument();
  expect(screen.getByText("Skill overlap · 20%")).toBeInTheDocument();
  expect(screen.getByText("Company quality · 15%")).toBeInTheDocument();
  expect(screen.getByText("Application effort · 10%")).toBeInTheDocument();
  expect(
    screen.getByText("Matches 2 of 2 detected technologies: FastAPI and Python."),
  ).toBeInTheDocument();

  await user.click(screen.getByRole("button", {name: "Include manual-review matches"}));
  expect(expand).toHaveBeenCalledWith({minimum_score: 60, include_maybe: true});
});
