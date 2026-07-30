import {cleanup, render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach, expect, test, vi} from "vitest";

import {DiscoveryLane} from "./DiscoveryLane";

afterEach(cleanup);

test("user can inspect screened roles by lane with understandable reasons", async () => {
  const ingest = vi.fn().mockResolvedValue(undefined);
  const user = userEvent.setup();
  const eligibleJob = {
    id: 1,
    source_url: "https://boards.greenhouse.io/acme/jobs/12345",
    fetched_at: "2026-07-29T12:00:00Z",
    company: "Acme Corp",
    title: "Junior Software Engineer",
    location: "New York, NY",
    description_text: "Build dependable tools for our operations team.",
    detected_requirements: ["Experience with Python", "Clear written communication"],
    source_platform: "greenhouse" as const,
    ats_posting_id: "12345",
    canonical_url: "https://boards.greenhouse.io/acme/jobs/12345",
    preferred_apply_url: "https://boards.greenhouse.io/acme/jobs/12345",
    snapshots: [
      {
        id: 1,
        source_url: "https://boards.greenhouse.io/acme/jobs/12345",
        fetched_at: "2026-07-29T12:00:00Z",
        company: "Acme Corp",
        title: "Junior Software Engineer",
        location: "New York, NY",
        description_text: "Build dependable tools for our operations team.",
        detected_requirements: ["Experience with Python", "Clear written communication"],
        source_platform: "greenhouse",
        ats_posting_id: "12345",
        canonical_url: "https://boards.greenhouse.io/acme/jobs/12345",
        raw_posting: {id: 12345},
      },
    ],
    screening: {
      lane: "eligible" as const,
      reasons: ["Target location: New York.", "Junior-friendly role: junior."],
    },
  };

  render(
    <DiscoveryLane
      jobs={[
        eligibleJob,
        {
          ...eligibleJob,
          id: 2,
          title: "Platform Engineer",
          screening: {
            lane: "stretch",
            reasons: ["Stretch experience requirement: 3 years."],
          },
        },
        {
          ...eligibleJob,
          id: 3,
          title: "Agency Full-Stack Engineer",
          screening: {
            lane: "maybe",
            reasons: ["Staffing-agency listing retained for manual review."],
          },
        },
        {
          ...eligibleJob,
          id: 4,
          title: "Senior Backend Engineer",
          screening: {
            lane: "rejected",
            reasons: ["Excluded seniority: senior role."],
          },
        },
      ]}
      ingesting={false}
      onIngest={ingest}
    />,
  );

  expect(screen.getByRole("heading", {name: "Eligible"})).toBeInTheDocument();
  expect(screen.getByRole("heading", {name: "Stretch"})).toBeInTheDocument();
  expect(screen.getByRole("heading", {name: "Maybe"})).toBeInTheDocument();
  expect(screen.getByRole("heading", {name: "Rejected"})).toBeInTheDocument();
  expect(
    screen.getByRole("heading", {name: "Junior Software Engineer", level: 4}),
  ).toBeInTheDocument();
  expect(screen.getAllByText("Acme Corp · New York, NY")).toHaveLength(8);
  expect(screen.getAllByText("Experience with Python")).toHaveLength(4);
  expect(screen.getAllByText("Clear written communication")).toHaveLength(4);
  expect(screen.getByText("Junior-friendly role: junior.")).toBeInTheDocument();
  expect(screen.getByText("Stretch experience requirement: 3 years.")).toBeInTheDocument();
  expect(
    screen.getByText("Staffing-agency listing retained for manual review."),
  ).toBeInTheDocument();
  expect(screen.getByText("Excluded seniority: senior role.")).toBeInTheDocument();
  expect(
    screen.getAllByRole("link", {name: "Apply via preferred source"})[0],
  ).toHaveAttribute(
    "href",
    "https://boards.greenhouse.io/acme/jobs/12345",
  );

  await user.click(screen.getByRole("button", {name: "Ingest configured sources"}));
  expect(ingest).toHaveBeenCalledOnce();
});

test("merged opportunity shows contributing sources and the preferred apply link", () => {
  const greenhouseSnapshot = {
    id: 1,
    source_url: "https://boards.greenhouse.io/acme/jobs/12345",
    fetched_at: "2026-07-29T12:00:00Z",
    company: "Acme Corp",
    title: "Junior Software Engineer",
    location: "New York, NY",
    description_text: "Build dependable tools.",
    detected_requirements: ["Experience with Python"],
    source_platform: "greenhouse",
    ats_posting_id: "12345",
    canonical_url: "https://boards.greenhouse.io/acme/jobs/12345",
    raw_posting: {id: 12345},
  };
  const linkedinSnapshot = {
    ...greenhouseSnapshot,
    id: 2,
    source_url: "https://www.linkedin.com/jobs/view/9876",
    source_platform: "linkedin",
    ats_posting_id: "9876",
    canonical_url: "https://www.linkedin.com/jobs/view/9876",
  };

  render(
    <DiscoveryLane
      jobs={[
        {
          ...greenhouseSnapshot,
          preferred_apply_url: "https://boards.greenhouse.io/acme/jobs/12345",
          snapshots: [greenhouseSnapshot, linkedinSnapshot],
          screening: {
            lane: "eligible",
            reasons: ["Target location: New York."],
          },
        },
      ]}
      ingesting={false}
      onIngest={vi.fn().mockResolvedValue(undefined)}
    />,
  );

  expect(
    screen.getByRole("heading", {name: "Junior Software Engineer", level: 4}),
  ).toBeInTheDocument();
  expect(screen.getByText("Sources: greenhouse, linkedin")).toBeInTheDocument();
  expect(screen.getByText("Snapshot history (2)")).toBeInTheDocument();
  expect(screen.getByRole("link", {name: "Apply via preferred source"})).toHaveAttribute(
    "href",
    "https://boards.greenhouse.io/acme/jobs/12345",
  );
  expect(screen.getByRole("link", {name: "greenhouse snapshot"})).toHaveAttribute(
    "href",
    "https://boards.greenhouse.io/acme/jobs/12345",
  );
  expect(screen.getByRole("link", {name: "linkedin snapshot"})).toHaveAttribute(
    "href",
    "https://www.linkedin.com/jobs/view/9876",
  );
  expect(screen.getAllByText("Build dependable tools.")).toHaveLength(3);
  expect(screen.getAllByText("Raw posting")).toHaveLength(2);
});
