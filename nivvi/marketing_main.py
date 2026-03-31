from __future__ import annotations

import csv
import io
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

try:
    import psycopg
except ImportError:  # pragma: no cover - optional runtime dependency
    psycopg = None


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9().\-\s]{7,32}$")
EVENTS = {
    "landing_view",
    "cta_click_nav",
    "cta_click_hero",
    "cta_click_midpage",
    "cta_click_final",
    "faq_expand",
    "waitlist_submit_success",
    "waitlist_submit_duplicate",
    "waitlist_submit_error",
}


class WaitlistRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    email: str = Field(min_length=5, max_length=254)
    phone_number: str | None = Field(default=None, max_length=32)
    marketing_consent: bool
    source: str | None = Field(default=None, max_length=64)
    utm: dict[str, str] | None = None

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("first_name is required")
        return trimmed

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_RE.fullmatch(normalized):
            raise ValueError("email must be valid")
        return normalized

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        if not PHONE_RE.fullmatch(trimmed):
            raise ValueError("phone_number must be valid")
        digits = re.sub(r"\D", "", trimmed)
        if not 7 <= len(digits) <= 15:
            raise ValueError("phone_number must be valid")
        return trimmed

    @field_validator("utm")
    @classmethod
    def validate_utm(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        sanitized: dict[str, str] = {}
        for key, raw in value.items():
            safe_key = str(key).strip()[:64]
            safe_val = str(raw).strip()[:256]
            if safe_key:
                sanitized[safe_key] = safe_val
        return sanitized


class WaitlistResponse(BaseModel):
    id: str
    status: Literal["created", "already_exists"]
    created_at: datetime


class AnalyticsEventRequest(BaseModel):
    event_name: str
    page: str = Field(default="landing", max_length=40)
    properties: dict[str, str] | None = None

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in EVENTS:
            raise ValueError("event_name is not supported")
        return normalized


@dataclass
class WaitlistLead:
    id: str
    first_name: str
    last_name: str | None
    email: str
    phone_number: str | None
    marketing_consent: bool
    source: str | None
    utm: dict[str, str]
    created_at: datetime


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
STORE_FILE = Path(os.getenv("NIVVI_WAITLIST_STORE", DATA_DIR / "waitlist_store.json"))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

store_lock = Lock()
waitlist_by_email: dict[str, WaitlistLead] = {}
analytics_events: list[dict] = []


def _serialize_lead(lead: WaitlistLead) -> dict:
    full_name = " ".join(part for part in [lead.first_name, lead.last_name] if part).strip()
    return {
        "id": lead.id,
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "full_name": full_name,
        "email": lead.email,
        "phone_number": lead.phone_number,
        "marketing_consent": lead.marketing_consent,
        "source": lead.source,
        "utm": lead.utm,
        "created_at": lead.created_at.isoformat(),
    }


def _hydrate_lead(raw: dict) -> WaitlistLead:
    created_at_raw = raw.get("created_at")
    created_at = datetime.fromisoformat(created_at_raw) if created_at_raw else datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return WaitlistLead(
        id=str(raw.get("id", uuid4().hex)),
        first_name=str(raw.get("first_name", "")).strip(),
        last_name=(str(raw.get("last_name", "")).strip() or None),
        email=str(raw.get("email", "")).strip().lower(),
        phone_number=(str(raw.get("phone_number", "")).strip() or None),
        marketing_consent=bool(raw.get("marketing_consent", True)),
        source=(str(raw.get("source", "")).strip() or None),
        utm={k: str(v) for k, v in (raw.get("utm") or {}).items()},
        created_at=created_at,
    )


def _load_store() -> None:
    if not STORE_FILE.exists():
        return
    try:
        payload = json.loads(STORE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return

    leads = payload.get("waitlist_leads", [])
    for raw in leads:
        lead = _hydrate_lead(raw)
        if lead.email:
            waitlist_by_email[lead.email] = lead


def _save_store() -> None:
    payload = {
        "waitlist_leads": [
            {
                **asdict(lead),
                "created_at": lead.created_at.isoformat(),
            }
            for lead in sorted(waitlist_by_email.values(), key=lambda item: item.created_at)
        ],
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    STORE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _connect_db():
    if psycopg is None:  # pragma: no cover
        raise RuntimeError("DATABASE_URL is set but psycopg is not installed")
    return psycopg.connect(DATABASE_URL)


def _db_row_to_lead(row: tuple) -> WaitlistLead:
    created_at = row[8]
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return WaitlistLead(
        id=row[0],
        first_name=row[1],
        last_name=row[2],
        email=row[3],
        phone_number=row[4],
        marketing_consent=row[5],
        source=row[6],
        utm=json.loads(row[7] or "{}"),
        created_at=created_at,
    )


def _db_init() -> None:
    with _connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS waitlist_leads (
                    id TEXT PRIMARY KEY,
                    first_name TEXT NOT NULL,
                    last_name TEXT,
                    email TEXT NOT NULL UNIQUE,
                    phone_number TEXT,
                    marketing_consent BOOLEAN NOT NULL,
                    source TEXT,
                    utm_json TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            conn.commit()


def _db_get_by_email(email: str) -> WaitlistLead | None:
    with _connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, first_name, last_name, email, phone_number, marketing_consent, source, utm_json, created_at
                FROM waitlist_leads
                WHERE email = %s
                LIMIT 1
                """,
                (email,),
            )
            row = cur.fetchone()
    if not row:
        return None
    return _db_row_to_lead(row)


def _db_insert_lead(lead: WaitlistLead) -> None:
    with _connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO waitlist_leads (
                    id, first_name, last_name, email, phone_number, marketing_consent, source, utm_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    lead.id,
                    lead.first_name,
                    lead.last_name,
                    lead.email,
                    lead.phone_number,
                    lead.marketing_consent,
                    lead.source,
                    json.dumps(lead.utm, separators=(",", ":"), sort_keys=True),
                    lead.created_at,
                ),
            )
            conn.commit()


def _db_list_leads(limit: int, source: str | None) -> tuple[int, list[WaitlistLead]]:
    where = " WHERE source = %s" if source else ""
    params: tuple = (source,) if source else tuple()

    with _connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM waitlist_leads{where}", params)
            total_count = int(cur.fetchone()[0])

            if source:
                cur.execute(
                    """
                    SELECT id, first_name, last_name, email, phone_number, marketing_consent, source, utm_json, created_at
                    FROM waitlist_leads
                    WHERE source = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (source, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, first_name, last_name, email, phone_number, marketing_consent, source, utm_json, created_at
                    FROM waitlist_leads
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            rows = cur.fetchall()

    return total_count, [_db_row_to_lead(row) for row in rows]


def _require_admin_key(request: Request) -> None:
    expected_key = os.getenv("NIVVI_ADMIN_KEY", "").strip()
    if not expected_key:
        raise HTTPException(status_code=503, detail="Admin key is not configured")

    provided_key = request.headers.get("x-admin-key", "").strip()
    if not provided_key or provided_key != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


if DATABASE_URL:
    _db_init()
else:
    _load_store()


app = FastAPI(
    title="Nivvi Marketing",
    version="1.0.0",
    description="Landing pages, waitlist capture, and marketing analytics endpoints.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/health")
def health() -> dict:
    backend = "database" if DATABASE_URL else "json_file"
    return {"status": "ok", "service": "marketing", "waitlist_backend": backend}


@app.post("/v1/waitlist", response_model=WaitlistResponse)
def create_waitlist_lead(payload: WaitlistRequest) -> WaitlistResponse:
    if not payload.marketing_consent:
        raise HTTPException(status_code=400, detail="marketing_consent must be true")

    if DATABASE_URL:
        existing = _db_get_by_email(payload.email)
        if existing:
            return WaitlistResponse(id=existing.id, status="already_exists", created_at=existing.created_at)

        lead = WaitlistLead(
            id=uuid4().hex,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            phone_number=payload.phone_number,
            marketing_consent=True,
            source=payload.source,
            utm=payload.utm or {},
            created_at=datetime.now(timezone.utc),
        )
        try:
            _db_insert_lead(lead)
        except Exception:
            # Protect against concurrent inserts on unique(email).
            existing = _db_get_by_email(payload.email)
            if existing:
                return WaitlistResponse(id=existing.id, status="already_exists", created_at=existing.created_at)
            raise
        return WaitlistResponse(id=lead.id, status="created", created_at=lead.created_at)

    with store_lock:
        existing = waitlist_by_email.get(payload.email)
        if existing:
            return WaitlistResponse(id=existing.id, status="already_exists", created_at=existing.created_at)

        lead = WaitlistLead(
            id=uuid4().hex,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            phone_number=payload.phone_number,
            marketing_consent=True,
            source=payload.source,
            utm=payload.utm or {},
            created_at=datetime.now(timezone.utc),
        )
        waitlist_by_email[lead.email] = lead
        _save_store()

    return WaitlistResponse(id=lead.id, status="created", created_at=lead.created_at)


@app.post("/v1/analytics/events")
def ingest_analytics_event(payload: AnalyticsEventRequest) -> dict:
    analytics_events.append(
        {
            "event_name": payload.event_name,
            "page": payload.page,
            "properties": payload.properties or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"status": "ok"}


@app.get("/v1/admin/waitlist/leads")
def list_waitlist_leads(
    request: Request,
    limit: int = Query(default=200, ge=1, le=5000),
    source: str | None = Query(default=None, max_length=64),
) -> dict:
    _require_admin_key(request)

    if DATABASE_URL:
        total_count, leads = _db_list_leads(limit=limit, source=source)
        rows = [_serialize_lead(lead) for lead in leads]
        return {"total_count": total_count, "returned_count": len(rows), "items": rows}

    leads = sorted(waitlist_by_email.values(), key=lambda item: item.created_at, reverse=True)
    if source:
        leads = [lead for lead in leads if lead.source == source]
    rows = [_serialize_lead(lead) for lead in leads[:limit]]
    return {"total_count": len(leads), "returned_count": len(rows), "items": rows}


@app.get("/v1/admin/waitlist/leads.csv")
def export_waitlist_leads_csv(request: Request, source: str | None = Query(default=None, max_length=64)) -> Response:
    _require_admin_key(request)

    if DATABASE_URL:
        _, leads = _db_list_leads(limit=5000, source=source)
    else:
        leads = sorted(waitlist_by_email.values(), key=lambda item: item.created_at, reverse=True)
        if source:
            leads = [lead for lead in leads if lead.source == source]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
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
        ]
    )
    for lead in leads:
        full_name = " ".join(part for part in [lead.first_name, lead.last_name] if part).strip()
        writer.writerow(
            [
                lead.id,
                lead.first_name,
                lead.last_name or "",
                full_name,
                lead.email,
                lead.phone_number or "",
                "true" if lead.marketing_consent else "false",
                lead.source or "",
                json.dumps(lead.utm, separators=(",", ":"), sort_keys=True),
                lead.created_at.isoformat(),
            ]
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="nivvi-waitlist-leads.csv"'},
    )


def _static_page(path: str, content_type: str | None = None):
    page = WEB_DIR / path
    if page.exists():
        return FileResponse(page, media_type=content_type)
    return JSONResponse(status_code=404, content={"detail": f"{path} not found"})


@app.get("/", response_model=None)
def root():
    if (WEB_DIR / "index.html").exists():
        return _static_page("index.html")
    return _static_page("landing.html")


@app.get("/waitlist", response_model=None)
def waitlist_page():
    return _static_page("waitlist.html")


@app.get("/waitlist/success", response_model=None)
def waitlist_success_page():
    return _static_page("waitlist-success.html")


@app.get("/legal/privacy", response_model=None)
def privacy_page():
    return _static_page("privacy.html")


@app.get("/legal/terms", response_model=None)
def terms_page():
    return _static_page("terms.html")


@app.get("/robots.txt", response_model=None)
def robots_page():
    return _static_page("robots.txt", content_type="text/plain; charset=utf-8")


@app.get("/sitemap.xml", response_model=None)
def sitemap_page():
    return _static_page("sitemap.xml", content_type="application/xml; charset=utf-8")
