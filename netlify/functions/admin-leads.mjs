import {
  jsonResponse,
  listLeads,
  requireAdmin,
  serializeLead,
} from "./_shared/waitlist.mjs";

export default async (request) => {
  if (request.method !== "GET") {
    return jsonResponse({ detail: "Method not allowed" }, 405);
  }

  const denied = requireAdmin(request);
  if (denied) return denied;

  const url = new URL(request.url);
  const limitRaw = Number.parseInt(url.searchParams.get("limit") || "200", 10);
  const limit = Number.isFinite(limitRaw) ? Math.min(Math.max(limitRaw, 1), 5000) : 200;
  const source = url.searchParams.get("source")?.trim() || null;

  const leads = await listLeads(source);
  const items = leads.slice(0, limit).map(serializeLead);
  return jsonResponse({
    total_count: leads.length,
    returned_count: items.length,
    items,
  });
};
