import {
  buildLead,
  errorResponse,
  getLeadByEmail,
  jsonResponse,
  readJson,
  saveLead,
  validateWaitlistPayload,
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
    payload = validateWaitlistPayload(raw);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Invalid request";
    const status = message.includes("must be valid") || message.includes("required") ? 422 : 400;
    return errorResponse(message, status);
  }

  const existing = await getLeadByEmail(payload.email);
  if (existing) {
    return jsonResponse({
      id: existing.id,
      status: "already_exists",
      created_at: existing.created_at,
    });
  }

  const lead = buildLead(payload);
  const result = await saveLead(lead);
  if (!result?.modified) {
    const duplicate = await getLeadByEmail(payload.email);
    if (duplicate) {
      return jsonResponse({
        id: duplicate.id,
        status: "already_exists",
        created_at: duplicate.created_at,
      });
    }
  }
  return jsonResponse({
    id: lead.id,
    status: "created",
    created_at: lead.created_at,
  });
};
