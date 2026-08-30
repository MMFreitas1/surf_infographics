"""The API comes up and answers."""

from surf import __version__


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": __version__}


def test_startup_creates_cache_dir(client, settings):
    assert settings.cache_dir.is_dir()
