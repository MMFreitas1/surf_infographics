"""FastAPI application. Localhost only -- no auth surface by design (ADR-0004)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from surf import __version__
from surf.config import Settings, get_settings
from surf.diagnostics import ErrorBuffer
from surf.ingest import IngestError, source_digest
from surf.ingest.stage import IngestStage
from surf.logging import configure_logging, get_logger
from surf.models import (
    Activity,
    ActivitySummary,
    LabelPass,
    LabelSource,
    PassKind,
    SessionCandidates,
    SessionTrack,
    StoredLabel,
    WaveLabel,
)
from surf.pipeline import StageCache, run_stage
from surf.pipeline.session import candidates_for, track_for
from surf.store import ActivityRepository, LabelRepository, StoreError

log = get_logger(__name__)


class ClientError(BaseModel):
    """An error reported by the browser UI, so it lands where the API's errors land."""

    message: str
    kind: str = "ClientError"
    stack: str = ""
    url: str = ""
    context: dict[str, Any] = Field(default_factory=dict)


class LabelCreate(WaveLabel):
    """What the labeling UI posts.

    ``verified`` loses its default on purpose. Inherited, it would default to False, and a
    UI that simply forgot the field would fill the store with labels that look complete and
    silently count for nothing -- ``counts_as_truth`` requires it. Making the caller say so
    turns a silent miss into a 422.
    """

    verified: bool
    supersedes: str | None = None
    """The label this one corrects. Nothing is edited; the old row stays (ADR-0006)."""


class PassCreate(BaseModel):
    """Recording that a labeller finished a sweep of a session."""

    kind: PassKind


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging and diagnostics for the app's lifetime."""
    settings: Settings = app.state.settings
    configure_logging(settings.log_level, settings.log_file)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    app.state.cache = StageCache(settings.cache_dir)
    app.state.activities = ActivityRepository(settings.db_path, app.state.cache)
    app.state.labels = LabelRepository(settings.db_path)
    log.info(
        "api.startup",
        version=__version__,
        data_dir=str(settings.data_dir),
        log_file=str(settings.log_file),
        db=str(settings.db_path),
    )
    yield
    app.state.activities.close()
    app.state.labels.close()
    log.info("api.shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Injectable settings keep tests hermetic."""
    app = FastAPI(title="Surf Infographics API", version=__version__, lifespan=lifespan)
    resolved = settings or get_settings()
    app.state.settings = resolved
    app.state.errors = ErrorBuffer(resolved.error_buffer_size)

    # The UI is a separate origin (:3000 against this :8000), so without this the browser
    # blocks every call before it leaves the tab -- including the one that reports errors,
    # which is how a CORS problem hides itself. Named origins only, never "*".
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.allowed_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

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

        # L0 runs through the pipeline runner, so an ingest is cached and replayed on
        # exactly the terms every later stage is: key, hit, or do the work and store it.
        try:
            result = run_stage(
                IngestStage(source_file=filename),
                request.app.state.cache,
                input_hash=digest,
                data=data,
            )
        except IngestError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        activity = result.output
        repo.save(
            activity,
            source_sha256=digest,
            samples_key=result.key,
            ingested_at=time.time(),
        )
        log.info(
            "activity.ingested",
            activity_id=activity.activity_id,
            fidelity=activity.fidelity.value,
            sport=activity.sport,
            samples=len(activity.samples),
            position_coverage=round(activity.position_coverage, 4),
            blind_seconds=activity.blind_seconds,
            from_cache=result.cached,
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

    def _stored_or_404(request: Request, activity_id: str) -> Activity:
        """The activity, or a 404. Every session-scoped route starts here."""
        repo: ActivityRepository = request.app.state.activities
        stored = repo.get(activity_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="no such activity")
        return stored

    def _samples_key_or_404(request: Request, activity_id: str) -> str:
        """Head of the stage chain for a stored session."""
        repo: ActivityRepository = request.app.state.activities
        key = repo.samples_key(activity_id)
        if key is None:  # pragma: no cover - _stored_or_404 raises first
            raise HTTPException(status_code=404, detail="no such activity")
        return key

    @app.get("/activities/{activity_id}/track")
    def read_track(request: Request, activity_id: str) -> SessionTrack:
        """The smoothed track and its shore-frame rotation, aligned row for row.

        Both tracks estimate every second, including the ~51% with no fix, so each row
        carries ``observed`` and the client is expected to draw the two states differently
        (ADR-0010). The frame is served with its reliability, not without it: an unreliable
        bearing is an answer, and hiding it would let the UI draw a confident wrong shore.
        """
        activity = _stored_or_404(request, activity_id)
        chain = track_for(
            activity,
            request.app.state.cache,
            samples_key=_samples_key_or_404(request, activity_id),
        )
        log.info(
            "track.served",
            activity_id=activity_id,
            seconds=len(chain.track.smoothed),
            reliable=chain.track.frame.reliable,
            from_cache=chain.cached,
        )
        return chain.track

    @app.get("/activities/{activity_id}/candidates")
    def read_candidates(request: Request, activity_id: str) -> SessionCandidates:
        """L3's proposals for this session.

        Deliberately a separate route from the track: the labeling UI has to be able to
        draw a session without ever fetching this, because the blind pass is the one that
        produces unanchored ground truth (ADR-0012).
        """
        activity = _stored_or_404(request, activity_id)
        proposed, cached = candidates_for(
            activity,
            request.app.state.cache,
            samples_key=_samples_key_or_404(request, activity_id),
        )
        log.info(
            "candidates.served",
            activity_id=activity_id,
            proposals=len(proposed.candidates),
            from_cache=cached,
        )
        return SessionCandidates(frame=proposed.frame, candidates=proposed.candidates)

    @app.post("/activities/{activity_id}/labels", status_code=201)
    def append_label(request: Request, activity_id: str, payload: LabelCreate) -> StoredLabel:
        """Append one human judgement. Nothing is ever updated in place (ADR-0006).

        A correction names the label it replaces; the replaced row stays exactly where it
        was, which is what keeps the history of how judgement changed readable.
        """
        _stored_or_404(request, activity_id)
        labels: LabelRepository = request.app.state.labels

        if payload.source is LabelSource.CIQ_BOOTSTRAP:
            raise HTTPException(
                status_code=400,
                detail="the API writes human labels only: bootstrap imports are not truth "
                "and do not enter through here (ADR-0006)",
            )
        if payload.source is LabelSource.HUMAN_ASSISTED and not labels.has_pass(
            activity_id, PassKind.BLIND
        ):
            raise HTTPException(
                status_code=409,
                detail="no blind pass on this session yet. Label it without candidates "
                "first, so an unanchored set exists to measure against (ADR-0012)",
            )

        try:
            stored = labels.append(
                activity_id,
                WaveLabel(**payload.model_dump(exclude={"supersedes", "counts_as_truth"})),
                created_at=time.time(),
                supersedes=payload.supersedes,
            )
        except StoreError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        log.info(
            "label.appended",
            activity_id=activity_id,
            label_id=stored.label_id,
            source=stored.source.value,
            is_wave=stored.is_wave,
            supersedes=stored.supersedes,
        )
        return stored

    @app.get("/activities/{activity_id}/labels")
    def read_labels(
        request: Request,
        activity_id: str,
        current: bool = False,
    ) -> list[StoredLabel]:
        """Labels for one session, oldest first.

        ``current=true`` drops superseded rows. The default is the whole record, because
        the audit trail is the reason this table is append-only in the first place.
        """
        _stored_or_404(request, activity_id)
        labels: LabelRepository = request.app.state.labels
        return labels.for_activity(activity_id, current=current)

    @app.post("/activities/{activity_id}/label-passes", status_code=201)
    def complete_pass(request: Request, activity_id: str, payload: PassCreate) -> LabelPass:
        """Record that a sweep of this session is finished.

        This is what separates "nobody has looked at this session" from "somebody looked
        carefully and there were no rides" -- and it is the gate the assisted pass opens
        against (ADR-0012).
        """
        _stored_or_404(request, activity_id)
        labels: LabelRepository = request.app.state.labels
        try:
            completed = labels.complete_pass(activity_id, payload.kind, completed_at=time.time())
        except StoreError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        log.info(
            "label_pass.completed",
            activity_id=activity_id,
            kind=completed.kind.value,
            label_count=completed.label_count,
        )
        return completed

    @app.get("/activities/{activity_id}/label-passes")
    def read_passes(request: Request, activity_id: str) -> list[LabelPass]:
        """Every completed sweep of this session, oldest first."""
        _stored_or_404(request, activity_id)
        labels: LabelRepository = request.app.state.labels
        return labels.passes_for(activity_id)

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
