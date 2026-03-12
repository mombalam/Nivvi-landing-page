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

## Notes

- Waitlist data is persisted to `data/waitlist_store.json` by default.
- Static assets are served from `web/` at `/static/*`.
