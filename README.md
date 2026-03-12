# Nivvi Landing + Waitlist

This repository is now scoped to the public marketing surface only:

- Landing page (`/`)
- Waitlist form (`/waitlist`)
- Waitlist success page (`/waitlist/success`)
- Legal placeholders (`/legal/privacy`, `/legal/terms`)
- Waitlist capture API (`POST /v1/waitlist`)
- Marketing analytics ingest (`POST /v1/analytics/events`)
- Admin lead export (`GET /v1/admin/waitlist/leads`, `GET /v1/admin/waitlist/leads.csv`)

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn marketing:app --reload --port 8002
```

Open:

- Landing: <http://127.0.0.1:8002/>
- Waitlist: <http://127.0.0.1:8002/waitlist>
- Success page: <http://127.0.0.1:8002/waitlist/success>
- API docs: <http://127.0.0.1:8002/docs>

## Waitlist admin access

Set a key before using admin endpoints:

```bash
export NIVVI_ADMIN_KEY="replace-with-strong-key"
```

Then call with header `x-admin-key`.

## Persistence

- Development fallback: local JSON file (`data/waitlist_store.json`).
- Production recommended: set `DATABASE_URL` (Postgres) so waitlist leads are durable across restarts/redeploys.

## Notes

- Waitlist data uses Postgres when `DATABASE_URL` is configured, otherwise JSON-file fallback.
- Static assets are served from `web/` at `/static/*`.
