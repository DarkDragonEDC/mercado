from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .database import Database
from .schemas import CreateLicenseRequest
from .security import (
    generate_license_key,
    hwid_digest,
    license_digest,
    masked_key,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class ProtocolResult:
    status_code: int
    payload: dict[str, Any]


class LicenseRepository:
    def __init__(self, database: Database, pepper: str):
        self.database = database
        self.pepper = pepper

    @staticmethod
    def _error(code: str, message: str, status_code: int = 403) -> ProtocolResult:
        return ProtocolResult(
            status_code,
            {"valid": False, "code": code, "message": message},
        )

    def _load_license(self, connection: sqlite3.Connection, key: str) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM licenses WHERE key_digest = ?",
            (license_digest(key, self.pepper),),
        ).fetchone()

    def _check_license(self, row: sqlite3.Row | None) -> ProtocolResult | None:
        if row is None:
            return self._error("INVALID_KEY", "Key invalida.", 404)
        if row["revoked_at"]:
            return self._error("REVOKED", "Esta licenca foi revogada.")
        if parse_iso(row["expires_at"]) <= utc_now():
            return self._error("EXPIRED", "Esta licenca esta expirada.")
        return None

    def _success(self, row: sqlite3.Row, newly_activated: bool) -> ProtocolResult:
        expires_at = parse_iso(row["expires_at"])
        remaining = max(0, int((expires_at - utc_now()).total_seconds()))
        return ProtocolResult(
            200,
            {
                "valid": True,
                "code": "OK",
                "expiresAt": iso(expires_at),
                "remainingSeconds": remaining,
                "newlyActivated": newly_activated,
                "modules": json.loads(row["modules_json"]),
            },
        )

    def activate(self, key: str, hwid: str, app_version: str) -> ProtocolResult:
        now = iso(utc_now())
        device_digest = hwid_digest(hwid, self.pepper)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._load_license(connection, key)
                error = self._check_license(row)
                if error:
                    connection.rollback()
                    return error
                assert row is not None
                device = connection.execute(
                    "SELECT 1 FROM license_devices WHERE license_id = ? AND hwid_digest = ?",
                    (row["id"], device_digest),
                ).fetchone()
                newly_activated = device is None
                if newly_activated:
                    count = connection.execute(
                        "SELECT COUNT(*) FROM license_devices WHERE license_id = ?",
                        (row["id"],),
                    ).fetchone()[0]
                    if count >= row["device_limit"]:
                        connection.rollback()
                        return self._error(
                            "DEVICE_LIMIT",
                            "O limite de computadores desta key foi atingido.",
                        )
                    connection.execute(
                        """INSERT INTO license_devices
                           (license_id, hwid_digest, first_seen_at, last_seen_at, app_version)
                           VALUES (?, ?, ?, ?, ?)""",
                        (row["id"], device_digest, now, now, app_version),
                    )
                else:
                    connection.execute(
                        """UPDATE license_devices SET last_seen_at = ?, app_version = ?
                           WHERE license_id = ? AND hwid_digest = ?""",
                        (now, app_version, row["id"], device_digest),
                    )
                connection.commit()
                return self._success(row, newly_activated)
            except Exception:
                connection.rollback()
                raise

    def validate(self, key: str, hwid: str, app_version: str) -> ProtocolResult:
        now = iso(utc_now())
        device_digest = hwid_digest(hwid, self.pepper)
        with self.database.connect() as connection:
            row = self._load_license(connection, key)
            error = self._check_license(row)
            if error:
                return error
            assert row is not None
            updated = connection.execute(
                """UPDATE license_devices SET last_seen_at = ?, app_version = ?
                   WHERE license_id = ? AND hwid_digest = ?""",
                (now, app_version, row["id"], device_digest),
            )
            if updated.rowcount == 0:
                return self._error(
                    "NOT_ACTIVATED", "Este computador ainda nao foi ativado."
                )
            return self._success(row, False)

    def create(self, request: CreateLicenseRequest) -> dict[str, Any]:
        created_at = utc_now()
        if request.duration_hours is not None:
            expires_at = created_at + timedelta(hours=request.duration_hours)
        else:
            expires_at = created_at + timedelta(days=request.duration_days or 30)

        for _ in range(10):
            raw_key = generate_license_key()
            license_id = str(uuid.uuid4())
            try:
                with self.database.connect() as connection:
                    connection.execute(
                        """INSERT INTO licenses
                           (id, key_digest, key_preview, discord_user_id, created_at,
                            expires_at, device_limit, modules_json, notes)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            license_id,
                            license_digest(raw_key, self.pepper),
                            masked_key(raw_key),
                            request.discord_user_id,
                            iso(created_at),
                            iso(expires_at),
                            request.device_limit,
                            json.dumps(request.modules, separators=(",", ":")),
                            request.notes,
                        ),
                    )
                return {
                    "id": license_id,
                    "key": raw_key,
                    "key_preview": masked_key(raw_key),
                    "expires_at": expires_at,
                    "device_limit": request.device_limit,
                    "modules": request.modules,
                }
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("nao foi possivel gerar uma key unica")

    def list(self, limit: int = 50, discord_user_id: str | None = None) -> list[dict[str, Any]]:
        where = ""
        parameters: list[Any] = []
        if discord_user_id:
            where = "WHERE l.discord_user_id = ?"
            parameters.append(discord_user_id)
        parameters.append(limit)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""SELECT l.*,
                       COUNT(d.hwid_digest) AS device_count,
                       MAX(d.last_seen_at) AS last_activity
                    FROM licenses l
                    LEFT JOIN license_devices d ON d.license_id = l.id
                    {where}
                    GROUP BY l.id
                    ORDER BY l.created_at DESC
                    LIMIT ?""",
                parameters,
            ).fetchall()
        return [self._summary(row) for row in rows]

    @staticmethod
    def _summary(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "key_preview": row["key_preview"],
            "discord_user_id": row["discord_user_id"],
            "created_at": parse_iso(row["created_at"]),
            "expires_at": parse_iso(row["expires_at"]),
            "revoked_at": parse_iso(row["revoked_at"]) if row["revoked_at"] else None,
            "device_limit": row["device_limit"],
            "device_count": row["device_count"],
            "modules": json.loads(row["modules_json"]),
            "notes": row["notes"],
            "last_activity": parse_iso(row["last_activity"]) if row["last_activity"] else None,
        }

    def revoke(self, license_id: str) -> bool:
        with self.database.connect() as connection:
            result = connection.execute(
                "UPDATE licenses SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (iso(utc_now()), license_id),
            )
            return result.rowcount == 1

    def reset_devices(self, license_id: str) -> bool:
        with self.database.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM licenses WHERE id = ?", (license_id,)
            ).fetchone()
            if not exists:
                return False
            connection.execute(
                "DELETE FROM license_devices WHERE license_id = ?", (license_id,)
            )
            return True

    def extend(self, license_id: str, days: int) -> datetime | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT expires_at FROM licenses WHERE id = ?", (license_id,)
            ).fetchone()
            if not row:
                return None
            current = parse_iso(row["expires_at"])
            base = max(current, utc_now())
            new_expiration = base + timedelta(days=days)
            connection.execute(
                "UPDATE licenses SET expires_at = ? WHERE id = ?",
                (iso(new_expiration), license_id),
            )
            return new_expiration

    def stats(self) -> dict[str, int]:
        now = iso(utc_now())
        soon = iso(utc_now() + timedelta(days=7))
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT
                    SUM(CASE WHEN revoked_at IS NULL AND expires_at > ? THEN 1 ELSE 0 END) AS active,
                    SUM(CASE WHEN revoked_at IS NULL AND expires_at > ? AND expires_at <= ? THEN 1 ELSE 0 END) AS soon,
                    SUM(CASE WHEN revoked_at IS NULL AND expires_at <= ? THEN 1 ELSE 0 END) AS expired,
                    SUM(CASE WHEN revoked_at IS NOT NULL THEN 1 ELSE 0 END) AS revoked,
                    COUNT(*) AS total
                   FROM licenses""",
                (now, now, soon, now),
            ).fetchone()
            devices = connection.execute(
                "SELECT COUNT(*) FROM license_devices"
            ).fetchone()[0]
        return {
            "active": row["active"] or 0,
            "expires_within_7_days": row["soon"] or 0,
            "expired": row["expired"] or 0,
            "revoked": row["revoked"] or 0,
            "devices": devices,
            "total": row["total"] or 0,
        }

