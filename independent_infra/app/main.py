from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .config import Settings
from .database import Database
from .repository import LicenseRepository, ProtocolResult
from .schemas import (
    CreateLicenseRequest,
    ExtendLicenseRequest,
    LicenseCreated,
    LicenseRequest,
    LicenseSummary,
    StatsResponse,
)
from .security import token_matches


class MinuteRateLimiter:
    def __init__(self, maximum: int):
        self.maximum = maximum
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, identity: str) -> bool:
        now = time.monotonic()
        cutoff = now - 60
        with self._lock:
            bucket = self._requests[identity]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.maximum:
                return False
            bucket.append(now)
            return True


def protocol_response(result: ProtocolResult) -> JSONResponse:
    return JSONResponse(status_code=result.status_code, content=result.payload)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()
    database = Database(resolved.database_path)
    repository = LicenseRepository(database, resolved.key_pepper)
    limiter = MinuteRateLimiter(resolved.rate_limit_per_minute)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        database.initialize()
        yield

    app = FastAPI(
        title="AlbionMKT Independent License API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.database = database
    app.state.repository = repository

    def require_admin(authorization: Annotated[str | None, Header()] = None) -> None:
        prefix = "Bearer "
        if not authorization or not authorization.startswith(prefix):
            raise HTTPException(status_code=401, detail="credencial administrativa ausente")
        provided = authorization[len(prefix) :]
        if not token_matches(provided, resolved.admin_token):
            raise HTTPException(status_code=403, detail="credencial administrativa invalida")

    def client_identity(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def rate_limited(request: Request) -> JSONResponse | None:
        if limiter.allow(client_identity(request)):
            return None
        return JSONResponse(
            status_code=429,
            content={
                "valid": False,
                "code": "RATE_LIMIT",
                "message": "Muitas tentativas. Aguarde um momento.",
            },
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/licenses/activate")
    def activate(request: Request, payload: LicenseRequest) -> JSONResponse:
        limited = rate_limited(request)
        if limited:
            return limited
        return protocol_response(
            repository.activate(payload.key, payload.hwid, payload.appVersion)
        )

    @app.post("/api/licenses/validate")
    def validate(request: Request, payload: LicenseRequest) -> JSONResponse:
        limited = rate_limited(request)
        if limited:
            return limited
        return protocol_response(
            repository.validate(payload.key, payload.hwid, payload.appVersion)
        )

    @app.post(
        "/api/admin/licenses",
        response_model=LicenseCreated,
        dependencies=[Depends(require_admin)],
    )
    def create_license(payload: CreateLicenseRequest) -> dict:
        return repository.create(payload)

    @app.get(
        "/api/admin/licenses",
        response_model=list[LicenseSummary],
        dependencies=[Depends(require_admin)],
    )
    def list_licenses(
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        discord_user_id: str | None = None,
    ) -> list[dict]:
        return repository.list(limit=limit, discord_user_id=discord_user_id)

    @app.post(
        "/api/admin/licenses/{license_id}/revoke",
        dependencies=[Depends(require_admin)],
    )
    def revoke_license(license_id: str) -> dict[str, bool]:
        if not repository.revoke(license_id):
            raise HTTPException(status_code=404, detail="licenca nao encontrada ou ja revogada")
        return {"ok": True}

    @app.post(
        "/api/admin/licenses/{license_id}/reset-devices",
        dependencies=[Depends(require_admin)],
    )
    def reset_devices(license_id: str) -> dict[str, bool]:
        if not repository.reset_devices(license_id):
            raise HTTPException(status_code=404, detail="licenca nao encontrada")
        return {"ok": True}

    @app.post(
        "/api/admin/licenses/{license_id}/extend",
        dependencies=[Depends(require_admin)],
    )
    def extend_license(license_id: str, payload: ExtendLicenseRequest) -> dict:
        expiration = repository.extend(license_id, payload.days)
        if expiration is None:
            raise HTTPException(status_code=404, detail="licenca nao encontrada")
        return {"ok": True, "expires_at": expiration}

    @app.get(
        "/api/admin/stats",
        response_model=StatsResponse,
        dependencies=[Depends(require_admin)],
    )
    def stats() -> dict[str, int]:
        return repository.stats()

    return app


app = create_app()

