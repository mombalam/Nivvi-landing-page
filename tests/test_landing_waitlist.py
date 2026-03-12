from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from nivvi.main import app


def test_landing_and_waitlist_pages_render() -> None:
    with TestClient(app) as client:
        landing = client.get("/")
        assert landing.status_code == 200
        assert "Wealth." in landing.text
        assert "Mastered." in landing.text
        assert "Get early access" in landing.text
        assert "Nivvi is your AI money manager." in landing.text
        assert 'href="/waitlist"' in landing.text

        waitlist = client.get("/waitlist")
        assert waitlist.status_code == 200
        assert "Join the Nivvi waitlist." in waitlist.text
        assert 'class="waitlist-form' in waitlist.text
        assert 'name="full_name"' in waitlist.text
        assert 'name="email"' in waitlist.text
        assert 'name="phone_number"' in waitlist.text

        success = client.get("/waitlist/success")
        assert success.status_code == 200
        assert "You&apos;re on the list" in success.text

        assert client.get("/legal/privacy").status_code == 200
        assert client.get("/legal/terms").status_code == 200
        assert client.get("/app").status_code == 404


def test_waitlist_create_and_dedupe() -> None:
    with TestClient(app) as client:
        email = f"lead_{uuid4().hex[:8]}@example.com"
        payload = {
            "first_name": "Ama",
            "last_name": "Mensah",
            "email": email,
            "phone_number": "+31 6 1234 5678",
            "marketing_consent": True,
            "source": "landing_hero",
            "utm": {"utm_source": "linkedin", "utm_campaign": "prelaunch"},
        }

        first = client.post("/v1/waitlist", json=payload)
        assert first.status_code == 200
        assert first.json()["status"] == "created"

        second = client.post("/v1/waitlist", json=payload)
        assert second.status_code == 200
        assert second.json()["status"] == "already_exists"
        assert second.json()["id"] == first.json()["id"]


@pytest.mark.parametrize(
    "event_name",
    [
        "landing_view",
        "cta_click_hero",
        "cta_click_midpage",
        "faq_expand",
    ],
)
def test_waitlist_validation_and_analytics(event_name: str) -> None:
    with TestClient(app) as client:
        bad_email = client.post(
            "/v1/waitlist",
            json={
                "first_name": "Kojo",
                "email": "invalid-email",
                "marketing_consent": True,
                "source": "landing_hero",
                "utm": {},
            },
        )
        assert bad_email.status_code == 422

        no_consent = client.post(
            "/v1/waitlist",
            json={
                "first_name": "Kojo",
                "email": f"kojo_{uuid4().hex[:8]}@example.com",
                "marketing_consent": False,
                "source": "landing_hero",
                "utm": {},
            },
        )
        assert no_consent.status_code == 400

        bad_phone = client.post(
            "/v1/waitlist",
            json={
                "first_name": "Kojo",
                "email": f"kojo_phone_{uuid4().hex[:8]}@example.com",
                "phone_number": "invalid-phone",
                "marketing_consent": True,
                "source": "landing_hero",
                "utm": {},
            },
        )
        assert bad_phone.status_code == 422

        analytics = client.post(
            "/v1/analytics/events",
            json={
                "event_name": event_name,
                "page": "landing",
                "properties": {"section": "hero"},
            },
        )
        assert analytics.status_code == 200
        assert analytics.json()["status"] == "ok"
