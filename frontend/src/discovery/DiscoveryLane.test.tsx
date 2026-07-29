import {cleanup, render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach, expect, test, vi} from "vitest";

import {DiscoveryLane} from "./DiscoveryLane";

afterEach(cleanup);

test("user can inspect a normalized role and ingest configured sources", async () => {
  const ingest = vi.fn().mockResolvedValue(undefined);
  const user = userEvent.setup();

  render(
    <DiscoveryLane
      jobs={[
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
        },
      ]}
      ingesting={false}
      onIngest={ingest}
    />,
  );

  expect(screen.getByRole("heading", {name: "Discovered"})).toBeInTheDocument();
  expect(screen.getByRole("heading", {name: "Junior Software Engineer"})).toBeInTheDocument();
  expect(screen.getByText("Acme Corp · New York, NY")).toBeInTheDocument();
  expect(screen.getByText("Experience with Python")).toBeInTheDocument();
  expect(screen.getByText("Clear written communication")).toBeInTheDocument();
  expect(screen.getByRole("link", {name: "View source"})).toHaveAttribute(
    "href",
    "https://boards.greenhouse.io/acme/jobs/12345",
  );

  await user.click(screen.getByRole("button", {name: "Ingest configured sources"}));
  expect(ingest).toHaveBeenCalledOnce();
});
