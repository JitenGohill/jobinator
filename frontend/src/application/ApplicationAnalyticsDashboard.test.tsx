import {cleanup, render, screen} from "@testing-library/react";
import {afterEach, expect, test, vi} from "vitest";

import {ApplicationAnalyticsDashboard} from "./ApplicationAnalyticsDashboard";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("dashboard presents transparent application analytics and distinguishes packets", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    packets_prepared: 5,
    applications_submitted: 2,
    applications_per_day: [{date: "2026-08-01", count: 2}],
    review_rejection_rate: {numerator: 1, denominator: 3, rate: 1 / 3},
    source_quality: [
      {source_platform: "company", applications: 2, responses: 1, recruiter_screens: 1, interviews: 1, rejections: 1, offers: 0},
    ],
    score_distribution: [
      {label: "90–100", minimum: 90, maximum: 100, count: 2},
    ],
    response_rate_by_role: [
      {group: "Backend Engineer", applications: 2, responses: 1, response_rate: 0.5},
    ],
    response_rate_by_source: [
      {group: "company", applications: 2, responses: 1, response_rate: 0.5},
    ],
    response_rate_by_company_type: [
      {group: "product", applications: 2, responses: 1, response_rate: 0.5},
    ],
    common_reject_reasons: [{reason: "Experience requirement", count: 1}],
    definitions: {
      review_rejection_rate: "Reviewed skips divided by completed review decisions.",
      source_quality: "Explicit responses divided by applications for each source.",
      response_rate: "Explicit responses divided by applications in the group.",
    },
  }), {status: 200, headers: {"Content-Type": "application/json"}})));

  render(<ApplicationAnalyticsDashboard />);

  expect(await screen.findByRole("heading", {name: "Application analytics"})).toBeInTheDocument();
  expect(screen.getByText("5 packets prepared")).toBeInTheDocument();
  expect(screen.getByText("2 applications submitted")).toBeInTheDocument();
  expect(screen.getByText("33.3% (1/3)")).toBeInTheDocument();
  expect(screen.getByText("2026-08-01: 2")).toBeInTheDocument();
  expect(screen.getByText("company: 2 applications · 1 responses · 1 interviews · 0 offers")).toBeInTheDocument();
  expect(screen.getByText("company: 50.0% (1/2)")).toBeInTheDocument();
  expect(screen.getByText("90–100: 2")).toBeInTheDocument();
  expect(screen.getByText("Experience requirement: 1")).toBeInTheDocument();
  expect(screen.getByText("Reviewed skips divided by completed review decisions.")).toBeInTheDocument();
});

test("empty analytics render as unavailable rates rather than invented zeroes", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    packets_prepared: 0,
    applications_submitted: 0,
    applications_per_day: [],
    review_rejection_rate: {numerator: 0, denominator: 0, rate: null},
    source_quality: [],
    score_distribution: [],
    response_rate_by_role: [],
    response_rate_by_source: [],
    response_rate_by_company_type: [],
    common_reject_reasons: [],
    definitions: {
      review_rejection_rate: "No denominator means no rate.",
      source_quality: "Explicit responses only.",
      response_rate: "Explicit responses only.",
    },
  }), {status: 200, headers: {"Content-Type": "application/json"}})));

  render(<ApplicationAnalyticsDashboard />);

  expect(await screen.findByText("Not available (0/0)")).toBeInTheDocument();
  expect(screen.getAllByText("No data yet.").length).toBeGreaterThan(0);
});
