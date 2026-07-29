import type {CanonicalProfile, SavedProfile} from "./types";

const profilePath = "/api/profile";

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as {detail?: string};
    return body.detail ?? `Request failed with status ${response.status}.`;
  } catch {
    return `Request failed with status ${response.status}.`;
  }
}

export async function loadProfile(): Promise<SavedProfile | null> {
  const response = await fetch(profilePath);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as SavedProfile;
}

export async function saveProfile(
  profile: CanonicalProfile,
  expectedVersion: number | null,
): Promise<SavedProfile> {
  const response = await fetch(profilePath, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      expected_version: expectedVersion,
      profile,
    }),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as SavedProfile;
}
