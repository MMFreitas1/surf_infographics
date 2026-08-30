"""Local error capture replaces SaaS error tracking (ADR-0007).

These endpoints are the debugging loop: if something breaks, it must be readable
over HTTP rather than lost to a terminal that has since scrolled.
"""

import pytest
from fastapi.testclient import TestClient

from surf.diagnostics import ErrorBuffer
from surf.main import create_app


def test_buffer_rejects_zero_capacity():
    with pytest.raises(ValueError, match="capacity must be positive"):
        ErrorBuffer(0)


def test_buffer_captures_type_message_and_traceback():
    buf = ErrorBuffer(10)
    try:
        msg = "boom"
        raise ValueError(msg)
    except ValueError as exc:
        captured = buf.capture(exc, path="/x")
    assert captured.kind == "ValueError"
    assert captured.message == "boom"
    assert "ValueError: boom" in captured.traceback
    assert captured.context["path"] == "/x"


def test_buffer_is_bounded_but_still_counts_everything():
    buf = ErrorBuffer(3)
    for i in range(10):
        buf.capture(RuntimeError(str(i)))
    assert len(buf) == 3
    assert buf.total_seen == 10
    assert [e.message for e in buf.recent()] == ["9", "8", "7"]


def test_recent_is_newest_first_and_respects_limit():
    buf = ErrorBuffer(10)
    for i in range(5):
        buf.capture(RuntimeError(str(i)))
    assert [e.message for e in buf.recent(2)] == ["4", "3"]


def test_clear_drops_retained_but_keeps_total():
    buf = ErrorBuffer(10)
    buf.capture(RuntimeError("x"))
    buf.clear()
    assert len(buf) == 0
    assert buf.total_seen == 1


def test_errors_endpoint_starts_empty(client):
    body = client.get("/diagnostics/errors").json()
    assert body["errors"] == []
    assert body["total_seen"] == 0


def test_ui_errors_are_reported_to_the_api(client):
    """Front-end failures are invisible outside the browser unless we route them here."""
    resp = client.post(
        "/diagnostics/client-error",
        json={
            "message": "Cannot read properties of undefined",
            "kind": "TypeError",
            "url": "http://127.0.0.1:3000/",
            "stack": "at Home (page.tsx:12)",
            "context": {"phase": "render"},
        },
    )
    assert resp.status_code == 201

    body = client.get("/diagnostics/errors").json()
    assert body["total_seen"] == 1
    err = body["errors"][0]
    assert err["message"] == "Cannot read properties of undefined"
    # the browser's own type and stack survive; they are not relabelled as a Python error
    assert err["kind"] == "TypeError"
    assert err["traceback"] == "at Home (page.tsx:12)"
    assert err["context"]["origin"] == "client"
    assert err["context"]["url"] == "http://127.0.0.1:3000/"


def test_clear_endpoint_empties_the_buffer(client):
    client.post("/diagnostics/client-error", json={"message": "x"})
    client.delete("/diagnostics/errors")
    body = client.get("/diagnostics/errors").json()
    assert body["errors"] == []
    assert body["total_seen"] == 1


def test_unhandled_server_errors_are_captured(settings):
    """An exception in a route must land in the buffer, not vanish."""
    app = create_app(settings)

    @app.get("/boom")
    def boom() -> None:
        msg = "kaboom"
        raise RuntimeError(msg)

    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/boom").status_code == 500
        body = c.get("/diagnostics/errors").json()

    assert body["total_seen"] == 1
    err = body["errors"][0]
    assert err["kind"] == "RuntimeError"
    assert err["message"] == "kaboom"
    assert err["context"]["path"] == "/boom"


def test_logs_endpoint_returns_startup_lines(client):
    body = client.get("/diagnostics/logs").json()
    assert any("api.startup" in line for line in body["lines"])
