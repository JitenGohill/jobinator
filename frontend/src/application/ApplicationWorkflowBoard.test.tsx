import {cleanup, render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach, expect, test, vi} from "vitest";

import {ApplicationWorkflowBoard} from "./ApplicationWorkflowBoard";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const packetReadyItem = {
  opportunity_id: 1,
  stage: "packet_ready",
  disposition: null,
  skip_reason: null,
  outcome: null,
  opportunity: {
    company: "Alpha Systems",
    title: "Junior Backend Engineer",
    location: "New York, NY",
    direct_apply_link: "https://careers.alpha.example/backend-engineer",
  },
  packet: {
    id: 7,
    profile_version: 3,
    opportunity_id: 1,
    score: {
      total: 91,
      weights: {},
      eligibility: {value: 100, explanation: "Eligible."},
      role_fit: {value: 90, explanation: "Strong role fit."},
      skill_overlap: {value: 90, explanation: "Matches Python."},
      company_quality: {value: 85, explanation: "Official listing."},
      application_effort: {value: 80, explanation: "Moderate form."},
    },
    job_snapshot: {id: 14},
    tailored_cv_draft: "# Tailored CV\n\nReliable backend engineer.",
    matched_profile_context: {
      skills: ["Python"],
      projects: ["Queue Lens"],
      work_experience: [],
    },
    missing_requirements: ["Kubernetes"],
    risk_flags: [{category: "missing_requirement", message: "Kubernetes is not evidenced."}],
    direct_apply_link: "https://careers.alpha.example/backend-engineer",
    estimated_application_effort: "moderate",
    cover_letter: null,
    screening_answers: [
      {question: "Why this role?", draft: "I build reliable systems.", review_required: true},
    ],
  },
  history: [
    {
      from_stage: "shortlisted",
      to_stage: "packet_ready",
      note: "Review packet prepared.",
      occurred_at: "2026-08-06T09:00:00Z",
    },
  ],
};

test("kanban exposes every stage and keeps packet review and manual handoff together", async () => {
  const reviewedItem = {...packetReadyItem, stage: "reviewed"};
  const appliedItem = {...packetReadyItem, stage: "applied"};
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({items: [packetReadyItem]}), {
        status: 200,
        headers: {"Content-Type": "application/json"},
      }),
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify(reviewedItem), {
        status: 200,
        headers: {"Content-Type": "application/json"},
      }),
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify(appliedItem), {
        status: 200,
        headers: {"Content-Type": "application/json"},
      }),
    );
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();

  render(<ApplicationWorkflowBoard refreshKey={1} />);

  for (const heading of [
    "Discovered",
    "Shortlisted",
    "Packet ready",
    "Reviewed",
    "Applied",
    "Rejected / skipped",
    "Follow-up",
    "Outcome",
  ]) {
    expect(await screen.findByRole("heading", {name: heading})).toBeInTheDocument();
  }
  expect(screen.getByText("91 / 100")).toBeInTheDocument();
  expect(screen.getByText("Kubernetes is not evidenced.")).toBeInTheDocument();
  expect(screen.getByText("Missing requirements: Kubernetes")).toBeInTheDocument();
  expect(screen.getByText("# Tailored CV")).toBeInTheDocument();
  expect(screen.getByText("Why this role?")).toBeInTheDocument();
  expect(screen.getByText("Review required")).toBeInTheDocument();
  expect(screen.getByText("Estimated effort: moderate")).toBeInTheDocument();
  expect(screen.getByRole("link", {name: "Open external application"})).toHaveAttribute(
    "href",
    packetReadyItem.packet.direct_apply_link,
  );
  expect(
    screen.getByText("Jobinator never fills or submits the external application."),
  ).toBeInTheDocument();

  await user.click(screen.getByRole("button", {name: "Mark packet reviewed"}));
  expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/application-workflow/1/transitions", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({target_stage: "reviewed"}),
  });
  expect(await screen.findByText("Ready for your external submission.")).toBeInTheDocument();

  await user.click(screen.getByRole("button", {name: "I completed submission externally"}));
  expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/application-workflow/1/transitions", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({target_stage: "applied", submitted_externally: true}),
  });
});

test("shortlisted opportunity sends user-entered screening questions for review", async () => {
  const shortlistedItem = {...packetReadyItem, stage: "shortlisted", packet: null};
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({items: [shortlistedItem]}), {status: 200}))
    .mockResolvedValueOnce(new Response(JSON.stringify(packetReadyItem.packet), {status: 200}))
    .mockResolvedValueOnce(new Response(JSON.stringify({items: [packetReadyItem]}), {status: 200}));
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();

  render(<ApplicationWorkflowBoard refreshKey={1} />);
  const questions = await screen.findByRole("textbox", {
    name: "Screening questions (one per line)",
  });
  await user.type(questions, "Why this role?\nDescribe a relevant project.");
  await user.click(screen.getByRole("button", {name: "Prepare review packet"}));

  expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/application-packets/1", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      cover_letter_requested: false,
      screening_questions: ["Why this role?", "Describe a relevant project."],
    }),
  });
  expect(await screen.findByText("Review required")).toBeInTheDocument();
});

test("user can record a skip reason from the dashboard", async () => {
  const shortlistedItem = {...packetReadyItem, stage: "shortlisted", packet: null};
  const skippedItem = {
    ...shortlistedItem,
    stage: "rejected_skipped",
    disposition: "skipped",
    skip_reason: "Role mismatch.",
  };
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({items: [shortlistedItem]}), {status: 200}))
    .mockResolvedValueOnce(new Response(JSON.stringify(skippedItem), {status: 200}));
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();

  render(<ApplicationWorkflowBoard refreshKey={1} />);
  await user.type(await screen.findByRole("textbox", {name: "Skip reason"}), "Role mismatch.");
  await user.click(screen.getByRole("button", {name: "Skip opportunity"}));

  expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/application-workflow/1/transitions", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({target_stage: "rejected_skipped", skip_reason: "Role mismatch."}),
  });
  expect(await screen.findByText("Skipped: Role mismatch.")).toBeInTheDocument();
});

test("dashboard reports a rejected transition without moving the card", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({items: [packetReadyItem]}), {status: 200}))
    .mockResolvedValueOnce(
      new Response(JSON.stringify({detail: "That workflow transition is not allowed."}), {
        status: 409,
        headers: {"Content-Type": "application/json"},
      }),
    );
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();

  render(<ApplicationWorkflowBoard refreshKey={1} />);
  await user.click(await screen.findByRole("button", {name: "Mark packet reviewed"}));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "That workflow transition is not allowed.",
  );
  expect(screen.getByRole("heading", {name: "Junior Backend Engineer"})).toBeInTheDocument();
});
