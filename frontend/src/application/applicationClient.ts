import type {ApplicationPacketPreview, ExportBundle} from "./types";

async function requireJson<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T;
  }
  try {
    const body = (await response.json()) as {detail?: string};
    throw new Error(body.detail ?? `Request failed with status ${response.status}.`);
  } catch (reason) {
    if (reason instanceof Error && !reason.message.startsWith("Unexpected token")) {
      throw reason;
    }
    throw new Error(`Request failed with status ${response.status}.`);
  }
}

export async function prepareApplicationPacket(
  opportunityId: number,
): Promise<ApplicationPacketPreview> {
  const response = await fetch(`/api/application-packets/${opportunityId}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({cover_letter_requested: false, screening_questions: []}),
  });
  return requireJson<ApplicationPacketPreview>(response);
}

export async function exportApplicationPacket(packetId: number): Promise<ExportBundle> {
  const response = await fetch(`/api/application-packets/${packetId}/exports`, {
    method: "POST",
  });
  return requireJson<ExportBundle>(response);
}
