"""Cross-origin access, which the UI cannot work without.

The web app runs on :3000 and this API on :8000. Those are different origins, so the browser
refuses every request before it is sent unless the API says otherwise -- and the refusal is
silent from the server's side, which is why this is worth pinning: nothing in the API log
would ever show it.
"""

from surf.config import Settings

WEB = "http://127.0.0.1:3000"


def test_the_local_ui_is_allowed_to_call_the_api(client):
    response = client.get("/activities", headers={"Origin": WEB})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WEB


def test_a_preflight_for_posting_a_label_is_answered(client):
    """The label POST sends Content-Type, so it is preflighted. Without this, no labelling."""
    response = client.options(
        "/activities/whatever/labels",
        headers={
            "Origin": WEB,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WEB
    assert "POST" in response.headers["access-control-allow-methods"]


def test_some_other_site_is_not(client):
    """This process serves someone's location history. It answers the local UI, not the web."""
    response = client.get("/activities", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in response.headers


def test_the_allowed_origins_are_configurable_and_never_a_wildcard():
    settings = Settings(SURF_WEB_ORIGINS="http://127.0.0.1:3000, http://localhost:3000 ,")
    assert settings.allowed_origins == ["http://127.0.0.1:3000", "http://localhost:3000"]
    assert "*" not in settings.allowed_origins
