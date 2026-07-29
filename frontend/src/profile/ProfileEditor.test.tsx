import {cleanup, render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach, expect, test, vi} from "vitest";

import {App} from "../App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function mockProfileRequests(
  loadProfileResponse: Response,
  saveProfileResponse: Response,
) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    if (input === "/api/discovery/jobs") {
      return new Response(JSON.stringify([]), {status: 200});
    }
    if (input === "/api/profile" && init?.method === "PUT") {
      return saveProfileResponse;
    }
    return loadProfileResponse;
  });
}

test("user can create a structured canonical profile", async () => {
  const fetchMock = mockProfileRequests(
    new Response(JSON.stringify({detail: "not found"}), {status: 404}),
    new Response(
      JSON.stringify({
        profile: {
          base_cv: "Backend engineer",
          projects: [],
          skills: [{name: "Python", proficiency: "advanced"}],
          preferred_stack: ["FastAPI", "React"],
          education: [],
          work_history: [],
          links: [],
          constraints: [],
          writing_samples: [],
          reusable_stories: [],
        },
        version: 1,
        updated_at: "2026-07-29T12:00:00Z",
      }),
      {status: 200, headers: {"Content-Type": "application/json"}},
    ),
  );
  const user = userEvent.setup();

  render(<App />);

  expect(await screen.findByRole("heading", {name: "Canonical profile"})).toBeInTheDocument();
  for (const section of [
    "Base CV",
    "Projects",
    "Skills",
    "Preferred stack",
    "Education",
    "Work history",
    "Links",
    "Constraints",
    "Writing samples",
    "Reusable stories",
  ]) {
    expect(screen.getByRole("heading", {name: section})).toBeInTheDocument();
  }

  await user.type(screen.getByRole("textbox", {name: "Base CV"}), "Backend engineer");
  await user.type(screen.getByRole("textbox", {name: /Preferred stack/}), "FastAPI, React");
  await user.click(screen.getByRole("button", {name: "Add skill"}));
  const skillsSection = screen.getByRole("region", {name: "Skills"});
  await user.type(within(skillsSection).getByLabelText("Name"), "Python");
  await user.selectOptions(within(skillsSection).getByLabelText("Proficiency"), "advanced");
  await user.click(screen.getByRole("button", {name: "Save profile"}));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  const saveRequest = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
  expect(saveRequest).toBeDefined();
  if (!saveRequest) {
    throw new Error("Expected a profile save request.");
  }
  expect(saveRequest[0]).toBe("/api/profile");
  expect(JSON.parse(String(saveRequest[1]?.body))).toEqual({
    expected_version: null,
    profile: {
      base_cv: "Backend engineer",
      projects: [],
      skills: [{name: "Python", proficiency: "advanced"}],
      preferred_stack: ["FastAPI", "React"],
      education: [],
      work_history: [],
      links: [],
      constraints: [],
      writing_samples: [],
      reusable_stories: [],
    },
  });
  expect(await screen.findByText("Saved version 1")).toBeInTheDocument();
});

test("user can view and update a saved profile", async () => {
  const existingProfile = {
    base_cv: "Original CV",
    projects: [],
    skills: [],
    preferred_stack: ["Python"],
    education: [],
    work_history: [],
    links: [],
    constraints: [],
    writing_samples: [],
    reusable_stories: [],
  };
  const fetchMock = mockProfileRequests(
    new Response(
      JSON.stringify({
        profile: existingProfile,
        version: 4,
        updated_at: "2026-07-29T12:00:00Z",
      }),
      {status: 200, headers: {"Content-Type": "application/json"}},
    ),
    new Response(
        JSON.stringify({
          profile: {...existingProfile, base_cv: "Updated CV"},
          version: 5,
          updated_at: "2026-07-29T12:05:00Z",
        }),
        {status: 200, headers: {"Content-Type": "application/json"}},
    ),
  );
  const user = userEvent.setup();

  render(<App />);

  const cv = await screen.findByRole("textbox", {name: "Base CV"});
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  expect(cv).toHaveValue("Original CV");
  await user.clear(cv);
  expect(cv).toHaveValue("");
  await user.type(cv, "Updated CV");
  await user.click(screen.getByRole("button", {name: "Save profile"}));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  const saveRequest = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
  expect(saveRequest).toBeDefined();
  if (!saveRequest) {
    throw new Error("Expected a profile save request.");
  }
  expect(JSON.parse(String(saveRequest[1]?.body))).toMatchObject({
    expected_version: 4,
    profile: {base_cv: "Updated CV"},
  });
  expect(await screen.findByText("Saved version 5")).toBeInTheDocument();
});
