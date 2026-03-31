import {
  leadsToCsv,
  listLeads,
  requireAdmin,
  textResponse,
} from "./_shared/waitlist.mjs";

export default async (request) => {
  if (request.method !== "GET") {
    return textResponse("Method not allowed", 405);
  }

  const denied = requireAdmin(request);
  if (denied) return denied;

  const url = new URL(request.url);
  const source = url.searchParams.get("source")?.trim() || null;
  const csv = leadsToCsv(await listLeads(source));
  return textResponse(csv, 200, {
    "content-type": "text/csv; charset=utf-8",
    "content-disposition": 'attachment; filename="nivvi-waitlist-leads.csv"',
  });
};
