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
