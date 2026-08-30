"""FastAPI application. Localhost only -- no auth surface by design (ADR-0004)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from surf import __version__
from surf.config import Settings, get_settings
from surf.diagnostics import ErrorBuffer
from surf.ingest import IngestError, parse_activity, source_digest
from surf.logging import configure_logging, get_logger
from surf.models import Activity, ActivitySummary
from surf.pipeline import StageCache
from surf.store import ActivityRepository

log = get_logger(__name__)


class ClientError(BaseModel):
    """An error reported by the browser UI, so it lands where the API's errors land."""

    message: str
    kind: str = "ClientError"
    stack: str = ""
    url: str = ""
    context: dict[str, Any] = Field(default_factory=dict)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging and diagnostics for the app's lifetime."""
    settings: Settings = app.state.settings
    configure_logging(settings.log_level, settings.log_file)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    app.state.activities = ActivityRepository(settings.db_path, StageCache(settings.cache_dir))
    log.info(
        "api.startup",
        version=__version__,
        data_dir=str(settings.data_dir),
        log_file=str(settings.log_file),
        db=str(settings.db_path),
    )
    yield
    app.state.activities.close()
    log.info("api.shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Injectable settings keep tests hermetic."""
    app = FastAPI(title="Surf Infographics API", version=__version__, lifespan=lifespan)
    resolved = settings or get_settings()
    app.state.settings = resolved
    app.state.errors = ErrorBuffer(resolved.error_buffer_size)

    @app.exception_handler(Exception)
    async def capture_unhandled(request: Request, exc: Exception) -> JSONResponse:
        """Record every unhandled error so it can be read back later."""
        buffer: ErrorBuffer = request.app.state.errors
        captured = buffer.capture(exc, path=request.url.path, method=request.method)
        log.error("api.unhandled", kind=captured.kind, message=captured.message)
        return JSONResponse(
            status_code=500,
            content={"detail": "internal error", "kind": captured.kind},
        )

    @app.get("/health")
    def health() -> dict[str, Any]:
        """Liveness probe."""
        return {"status": "ok", "version": __version__}

    @app.post("/activities", status_code=201)
    async def ingest_activity(
        request: Request,
        response: Response,
        filename: Annotated[str, Query(max_length=255)] = "",
    ) -> Activity:
        """Ingest an activity file posted as the raw request body.

        The body is the file's bytes -- the format is detected from its content, so
        ``filename`` is recorded for display only and never decides how it is parsed.
        Posting identical bytes twice returns the activity already stored, with 200
        rather than 201, so a repeated upload cannot fork one session into two.
        """
        cfg: Settings = request.app.state.settings
        repo: ActivityRepository = request.app.state.activities

        data = await request.body()
        if not data:
            raise HTTPException(status_code=400, detail="empty body: post the file's bytes")
        if len(data) > cfg.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"file is larger than the {cfg.max_upload_bytes} byte limit",
            )

        digest = source_digest(data)
        existing = repo.id_for_digest(digest)
        if existing is not None:
            stored = repo.get(existing)
            if stored is not None:
                response.status_code = 200
                log.info("activity.already_ingested", activity_id=existing)
                return stored

        try:
            activity = parse_activity(data, source_file=filename)
        except IngestError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        repo.save(activity, source_sha256=digest, ingested_at=time.time())
        log.info(
            "activity.ingested",
            activity_id=activity.activity_id,
            fidelity=activity.fidelity.value,
            sport=activity.sport,
            samples=len(activity.samples),
            position_coverage=round(activity.position_coverage, 4),
            blind_seconds=activity.blind_seconds,
        )
        return activity

    @app.get("/activities")
    def list_activities(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[ActivitySummary]:
        """Stored activities without their samples, newest session first."""
        repo: ActivityRepository = request.app.state.activities
        return repo.summaries(limit)

    @app.get("/activities/{activity_id}")
    def read_activity(request: Request, activity_id: str) -> Activity:
        """One activity in the canonical shape, samples included."""
        repo: ActivityRepository = request.app.state.activities
        stored = repo.get(activity_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="no such activity")
        return stored

    @app.get("/diagnostics/errors")
    def read_errors(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    ) -> dict[str, Any]:
        """Recent errors, newest first. Replaces SaaS error tracking (ADR-0007)."""
        buffer: ErrorBuffer = request.app.state.errors
        return {
            "total_seen": buffer.total_seen,
            "retained": len(buffer),
            "capacity": buffer.capacity,
            "errors": [e.as_dict() for e in buffer.recent(limit)],
        }

    @app.delete("/diagnostics/errors")
    def clear_errors(request: Request) -> dict[str, Any]:
        """Drop retained errors, so a debugging run starts from a clean slate."""
        buffer: ErrorBuffer = request.app.state.errors
        buffer.clear()
        return {"retained": len(buffer), "total_seen": buffer.total_seen}

    @app.post("/diagnostics/client-error", status_code=201)
    def report_client_error(request: Request, payload: ClientError) -> dict[str, Any]:
        """Accept an error from the browser UI.

        Front-end failures are otherwise invisible outside the browser console. Routing
        them here puts UI and API errors in one place that is readable over HTTP.
        """
        buffer: ErrorBuffer = request.app.state.errors
        captured = buffer.record(
            kind=payload.kind,
            message=payload.message,
            traceback_text=payload.stack,
            origin="client",
            url=payload.url,
            **payload.context,
        )
        log.error("ui.error", kind=payload.kind, message=payload.message, url=payload.url)
        return {"recorded": True, "timestamp": captured.timestamp}

    @app.get("/diagnostics/logs")
    def read_logs(
        request: Request,
        lines: Annotated[int, Query(ge=1, le=5000)] = 200,
    ) -> dict[str, Any]:
        """Tail the structured log file."""
        cfg: Settings = request.app.state.settings
        if not cfg.log_file.is_file():
            return {"file": str(cfg.log_file), "lines": []}
        content = cfg.log_file.read_text(encoding="utf-8").splitlines()
        return {"file": str(cfg.log_file), "lines": content[-lines:]}

    return app


app = create_app()
