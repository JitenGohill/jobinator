import {cleanup, render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach, expect, test, vi} from "vitest";

import {DiscoveryDashboard} from "./DiscoveryDashboard";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("dashboard reports each source result after ingesting configured sources", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify([]), {status: 200}))
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail: "Save the canonical profile before generating a candidate queue.",
        }),
        {status: 409},
      ),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify([]), {status: 200}))
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify([
          {id: "linkedin", label: "LinkedIn", domains: ["linkedin.com"]},
          {id: "engineering-list", label: "Engineering list", domains: []},
        ]),
        {status: 200},
      ),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          discovered: 1,
          sources: [
            {
              platform: "lever",
              identifier: "acme",
              status: "succeeded",
              discovered: 1,
              error: null,
            },
            {
              platform: "ashby",
              identifier: "acme",
              status: "failed",
              discovered: 0,
              error: "Ashby returned an invalid posting.",
            },
          ],
        }),
        {status: 200},
      ),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify([]), {status: 200}))
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail: "Save the canonical profile before generating a candidate queue.",
        }),
        {status: 409},
      ),
    );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();

  render(<DiscoveryDashboard />);
  await screen.findByText("No roles discovered yet.");
  await user.click(screen.getByRole("button", {name: "Ingest configured sources"}));

  await waitFor(() => {
    expect(screen.getByText("lever (acme): discovered 1")).toBeInTheDocument();
  });
  expect(
    screen.getByText("ashby (acme): Ashby returned an invalid posting."),
  ).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("1 snapshot discovered");
});

test("user can confirm sources for many links and review unresolved links", async () => {
  const linkedinUrl = "https://www.linkedin.com/jobs/view/987654321";
  const wellfoundUrl = "https://wellfound.com/jobs/12345-junior-engineer";
  const unresolvedLink = {
    id: 1,
    url: linkedinUrl,
    source_platform: "linkedin",
    status: "unresolved",
    resolved_url: null,
    snapshot_id: null,
    reason:
      "LinkedIn links are preserved for manual review; automated LinkedIn browsing was not attempted.",
    created_at: "2026-08-05T12:00:00Z",
  };
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (input === "/api/discovery/jobs") {
      return new Response(JSON.stringify([]), {status: 200});
    }
    if (input === "/api/discovery/links" && init?.method === "POST") {
      return new Response(
        JSON.stringify({discovered: 0, links: [unresolvedLink]}),
        {status: 200},
      );
    }
    if (input === "/api/discovery/links") {
      return new Response(JSON.stringify([]), {status: 200});
    }
    if (input === "/api/discovery/link-sources") {
      return new Response(
        JSON.stringify([
          {id: "linkedin", label: "LinkedIn", domains: ["linkedin.com"]},
          {id: "wellfound", label: "Wellfound", domains: ["wellfound.com"]},
          {id: "engineering-list", label: "Engineering list", domains: []},
        ]),
        {status: 200},
      );
    }
    if (String(input).startsWith("/api/discovery/queue?")) {
      return new Response(
        JSON.stringify({
          detail: "Save the canonical profile before generating a candidate queue.",
        }),
        {status: 409},
      );
    }
    throw new Error(`Unexpected request: ${String(input)}`);
  });
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();

  render(<DiscoveryDashboard />);
  await screen.findByText("No roles discovered yet.");
  await user.type(
    screen.getByRole("textbox", {name: "Discovery links"}),
    `${linkedinUrl}\n${wellfoundUrl}`,
  );

  expect(screen.getByLabelText(`Source for ${linkedinUrl}`)).toHaveValue(
    "engineering-list",
  );
  await user.selectOptions(
    screen.getByLabelText(`Source for ${linkedinUrl}`),
    "linkedin",
  );
  await user.selectOptions(
    screen.getByLabelText(`Source for ${wellfoundUrl}`),
    "engineering-list",
  );
  await user.click(screen.getByRole("button", {name: "Add discovery links"}));

  await screen.findByText(unresolvedLink.reason);
  expect(screen.getByRole("link", {name: "Review manually"})).toHaveAttribute(
    "href",
    linkedinUrl,
  );
  expect(fetch).toHaveBeenCalledWith("/api/discovery/links", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      links: [
        {url: linkedinUrl, source_platform: "linkedin"},
        {url: wellfoundUrl, source_platform: "engineering-list"},
      ],
    }),
  });
});
