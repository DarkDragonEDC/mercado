from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("ALBIONMKT_ADMIN_TOKEN", "test-admin-token-00000000000000000000")
os.environ.setdefault("ALBIONMKT_KEY_PEPPER", "test-key-pepper-000000000000000000000")

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


ADMIN_TOKEN = "admin-token-for-tests-000000000000000"
PEPPER = "pepper-for-tests-000000000000000000000"
HWID_A = "a" * 64
HWID_B = "b" * 64


def make_client(tmp_path: Path, rate_limit: int = 100) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "licenses.db",
        admin_token=ADMIN_TOKEN,
        key_pepper=PEPPER,
        rate_limit_per_minute=rate_limit,
    )
    return TestClient(create_app(settings))


def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def create_license(client: TestClient, **overrides) -> dict:
    body = {
        "discord_user_id": "1366066241667862680",
        "duration_days": 30,
        "device_limit": 1,
        "modules": ["purchase_orders", "sales_orders"],
    }
    body.update(overrides)
    response = client.post(
        "/api/admin/licenses", json=body, headers=admin_headers()
    )
    assert response.status_code == 200, response.text
    return response.json()


def license_request(key: str, hwid: str = HWID_A) -> dict[str, str]:
    return {"key": key, "hwid": hwid, "appVersion": "2.7.1"}


def test_health_and_admin_authentication(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/admin/stats").status_code == 401
        assert (
            client.get(
                "/api/admin/stats", headers={"Authorization": "Bearer errado"}
            ).status_code
            == 403
        )


def test_full_license_lifecycle(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        created = create_license(client)
        key = created["key"]

        not_activated = client.post(
            "/api/licenses/validate", json=license_request(key)
        )
        assert not_activated.status_code == 403
        assert not_activated.json()["code"] == "NOT_ACTIVATED"

        activated = client.post(
            "/api/licenses/activate", json=license_request(key)
        )
        assert activated.status_code == 200
        assert activated.json()["newlyActivated"] is True
        assert activated.json()["modules"] == ["purchase_orders", "sales_orders"]

        repeated = client.post(
            "/api/licenses/activate", json=license_request(key)
        )
        assert repeated.status_code == 200
        assert repeated.json()["newlyActivated"] is False

        validated = client.post(
            "/api/licenses/validate", json=license_request(key)
        )
        assert validated.status_code == 200
        assert validated.json()["code"] == "OK"

        device_limit = client.post(
            "/api/licenses/activate", json=license_request(key, HWID_B)
        )
        assert device_limit.status_code == 403
        assert device_limit.json()["code"] == "DEVICE_LIMIT"

        listed = client.get(
            "/api/admin/licenses?limit=10", headers=admin_headers()
        ).json()
        assert listed[0]["device_count"] == 1
        assert key not in str(listed)

        stats = client.get("/api/admin/stats", headers=admin_headers()).json()
        assert stats["active"] == 1
        assert stats["devices"] == 1

        reset = client.post(
            f"/api/admin/licenses/{created['id']}/reset-devices",
            headers=admin_headers(),
        )
        assert reset.status_code == 200
        assert (
            client.post(
                "/api/licenses/activate", json=license_request(key, HWID_B)
            ).status_code
            == 200
        )

        revoked = client.post(
            f"/api/admin/licenses/{created['id']}/revoke",
            headers=admin_headers(),
        )
        assert revoked.status_code == 200
        rejected = client.post(
            "/api/licenses/validate", json=license_request(key, HWID_B)
        )
        assert rejected.status_code == 403
        assert rejected.json()["code"] == "REVOKED"


def test_invalid_key_and_rate_limit(tmp_path: Path) -> None:
    with make_client(tmp_path, rate_limit=1) as client:
        first = client.post(
            "/api/licenses/activate",
            json=license_request("ALBIONMKT-AAAAA-BBBBB-CCCCC-DDDDD"),
        )
        assert first.status_code == 404
        assert first.json()["code"] == "INVALID_KEY"

        limited = client.post(
            "/api/licenses/activate",
            json=license_request("ALBIONMKT-AAAAA-BBBBB-CCCCC-DDDDD"),
        )
        assert limited.status_code == 429
        assert limited.json()["code"] == "RATE_LIMIT"


def test_extend_license(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        created = create_license(client)
        response = client.post(
            f"/api/admin/licenses/{created['id']}/extend",
            json={"days": 5},
            headers=admin_headers(),
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

