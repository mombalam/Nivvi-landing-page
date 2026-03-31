import { getStore } from "@netlify/blobs";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const PHONE_RE = /^\+?[0-9().\-\s]{7,32}$/;

export const EVENTS = new Set([
  "landing_view",
  "cta_click_nav",
  "cta_click_hero",
  "cta_click_midpage",
  "cta_click_final",
  "faq_expand",
  "waitlist_submit_success",
  "waitlist_submit_duplicate",
  "waitlist_submit_error",
]);

export function jsonResponse(payload, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      ...extraHeaders,
    },
  });
}

export function textResponse(body, status = 200, extraHeaders = {}) {
  return new Response(body, {
    status,
    headers: {
      "content-type": "text/plain; charset=utf-8",
      ...extraHeaders,
    },
  });
}

export function errorResponse(detail, status = 400) {
  return jsonResponse({ detail }, status);
}

export async function readJson(request) {
  try {
    return await request.json();
  } catch {
    return null;
  }
}

function cleanString(value, maxLength) {
  const trimmed = String(value ?? "").trim();
  return trimmed.slice(0, maxLength);
}

export function sanitizeUtm(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return {};
  }
  const sanitized = {};
  for (const [key, value] of Object.entries(raw)) {
    const safeKey = cleanString(key, 64);
    const safeValue = cleanString(value, 256);
    if (safeKey) sanitized[safeKey] = safeValue;
  }
  return sanitized;
}

export function validateWaitlistPayload(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("Invalid JSON payload");
  }

  const firstName = cleanString(raw.first_name, 80);
  if (!firstName) {
    throw new Error("first_name is required");
  }

  const lastName = cleanString(raw.last_name, 80) || null;
  const email = cleanString(raw.email, 254).toLowerCase();
  if (!EMAIL_RE.test(email)) {
    throw new Error("email must be valid");
  }

  const phoneNumber = cleanString(raw.phone_number, 32) || null;
  if (phoneNumber) {
    if (!PHONE_RE.test(phoneNumber)) {
      throw new Error("phone_number must be valid");
    }
    const digits = phoneNumber.replace(/\D/g, "");
    if (digits.length < 7 || digits.length > 15) {
      throw new Error("phone_number must be valid");
    }
  }

  if (raw.marketing_consent !== true) {
    throw new Error("marketing_consent must be true");
  }

  return {
    first_name: firstName,
    last_name: lastName,
    email,
    phone_number: phoneNumber,
    marketing_consent: true,
    source: cleanString(raw.source, 64) || null,
    utm: sanitizeUtm(raw.utm),
  };
}

export function validateAnalyticsPayload(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("Invalid JSON payload");
  }
  const eventName = cleanString(raw.event_name, 80);
  if (!EVENTS.has(eventName)) {
    throw new Error("event_name is not supported");
  }
  const page = cleanString(raw.page || "landing", 40) || "landing";
  const properties = sanitizeUtm(raw.properties);
  return { event_name: eventName, page, properties };
}

export function waitlistStore() {
  return getStore("waitlist");
}

export function analyticsStore() {
  return getStore("analytics");
}

function leadKey(email) {
  return `lead/${encodeURIComponent(email)}`;
}

export async function getLeadByEmail(email) {
  return waitlistStore().get(leadKey(email), { type: "json" });
}

export function buildLead(payload) {
  return {
    id: crypto.randomUUID().replace(/-/g, ""),
    first_name: payload.first_name,
    last_name: payload.last_name,
    email: payload.email,
    phone_number: payload.phone_number,
    marketing_consent: true,
    source: payload.source,
    utm: payload.utm,
    created_at: new Date().toISOString(),
  };
}

export async function saveLead(lead) {
  return waitlistStore().set(leadKey(lead.email), JSON.stringify(lead), { onlyIfNew: true });
}

export function serializeLead(lead) {
  return {
    ...lead,
    full_name: [lead.first_name, lead.last_name].filter(Boolean).join(" ").trim(),
  };
}

export async function listLeads(source = null) {
  const { blobs } = await waitlistStore().list({ prefix: "lead/" });
  const rawLeads = await Promise.all(blobs.map((blob) => waitlistStore().get(blob.key, { type: "json" })));
  const leads = rawLeads.filter(Boolean);
  const filtered = source ? leads.filter((lead) => lead.source === source) : leads;
  return filtered.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
}

export function requireAdmin(request) {
  const expectedKey = String(process.env.NIVVI_ADMIN_KEY || "").trim();
  if (!expectedKey) {
    return errorResponse("Admin key is not configured", 503);
  }
  const providedKey = request.headers.get("x-admin-key")?.trim() || "";
  if (!providedKey || providedKey !== expectedKey) {
    return errorResponse("Unauthorized", 401);
  }
  return null;
}

function csvCell(value) {
  const text = String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
}

export function leadsToCsv(leads) {
  const lines = [
    [
      "id",
      "first_name",
      "last_name",
      "full_name",
      "email",
      "phone_number",
      "marketing_consent",
      "source",
      "utm_json",
      "created_at",
    ].join(","),
  ];

  for (const lead of leads) {
    const row = serializeLead(lead);
    lines.push(
      [
        csvCell(row.id),
        csvCell(row.first_name),
        csvCell(row.last_name || ""),
        csvCell(row.full_name),
        csvCell(row.email),
        csvCell(row.phone_number || ""),
        csvCell(row.marketing_consent ? "true" : "false"),
        csvCell(row.source || ""),
        csvCell(JSON.stringify(row.utm || {}, Object.keys(row.utm || {}).sort())),
        csvCell(row.created_at),
      ].join(",")
    );
  }

  return lines.join("\n");
}

export async function recordAnalyticsEvent(payload) {
  const event = {
    event_name: payload.event_name,
    page: payload.page,
    properties: payload.properties,
    created_at: new Date().toISOString(),
  };
  const key = `event/${Date.now()}-${Math.random().toString(36).slice(2, 10)}.json`;
  await analyticsStore().set(key, JSON.stringify(event));
}
