# Landing Deployment

## Scope

This service is landing-only. It includes the public pages and waitlist capture API.

## Start command

```bash
uvicorn marketing:app --host 0.0.0.0 --port $PORT
```

## Required environment

- `NIVVI_ADMIN_KEY` for admin lead listing/export endpoints.
- Optional: `NIVVI_WAITLIST_STORE` (path override for waitlist JSON file).
- Recommended for production: `DATABASE_URL` (Postgres) for durable waitlist persistence.

## Endpoints

- `GET /`
- `GET /waitlist`
- `GET /waitlist/success`
- `GET /legal/privacy`
- `GET /legal/terms`
- `POST /v1/waitlist`
- `POST /v1/analytics/events`
- `GET /v1/admin/waitlist/leads`
- `GET /v1/admin/waitlist/leads.csv`

## Render quick setup

1. Create a **Web Service** from this repo.
2. Set start command above.
3. Add env var `NIVVI_ADMIN_KEY`.
4. Deploy.
5. If possible, attach a Postgres instance and set `DATABASE_URL`.
