import { jsonResponse } from "./_shared/waitlist.mjs";

export default async () =>
  jsonResponse({
    status: "ok",
    service: "marketing",
    waitlist_backend: "netlify_blobs",
  });
