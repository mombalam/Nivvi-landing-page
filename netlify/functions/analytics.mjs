import {
  errorResponse,
  jsonResponse,
  readJson,
  recordAnalyticsEvent,
  validateAnalyticsPayload,
} from "./_shared/waitlist.mjs";

export default async (request) => {
  if (request.method !== "POST") {
    return errorResponse("Method not allowed", 405);
  }

  const raw = await readJson(request);
  if (!raw) {
    return errorResponse("Invalid JSON payload", 400);
  }

  let payload;
  try {
    payload = validateAnalyticsPayload(raw);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Invalid request";
    return errorResponse(message, 422);
  }

  await recordAnalyticsEvent(payload);
  return jsonResponse({ status: "ok" });
};
