"""The satellite basemap: fetched once, then served from disk forever.

The property that matters is the one `architecture.md` section 7 asks for — **a session
opens with no network** — so most of what follows is about the second request, not the
first, and about what happens when upstream is simply not there.

Every test here runs offline. `httpx.get` is replaced rather than reached; a test suite that
quietly fetches from Esri would pass on this laptop and fail in CI, which is the failure mode
the rule in CLAUDE.md exists to prevent.
"""

from pathlib import Path

import httpx
import pytest

from surf.basemap import ATTRIBUTION, MAX_ZOOM, MIN_ZOOM, TileCache, TileError

JPEG = b"\xff\xd8\xff\xe0 pretend this is imagery \xff\xd9"


class Upstream:
    """A stand-in for Esri that counts how often it was asked."""

    def __init__(self, *, data: bytes = JPEG, fail: bool = False) -> None:
        self.data = data
        self.fail = fail
        self.calls: list[str] = []

    def __call__(self, url: str, **_: object) -> httpx.Response:
        self.calls.append(url)
        if self.fail:
            raise httpx.ConnectError("no network")
        return httpx.Response(200, content=self.data, request=httpx.Request("GET", url))


@pytest.fixture
def upstream(monkeypatch) -> Upstream:
    fake = Upstream()
    monkeypatch.setattr("surf.basemap.httpx.get", fake)
    return fake


@pytest.fixture
def cache(tmp_path: Path) -> TileCache:
    return TileCache(tmp_path / "tiles")


# -- fetching, and then not fetching -----------------------------------------------------


def test_the_first_request_fetches_and_the_second_does_not(cache, upstream):
    """The whole point. One trip upstream per tile, ever."""
    first = cache.get(16, 100, 200)
    second = cache.get(16, 100, 200)

    assert first.data == JPEG
    assert first.cached is False
    assert second.data == JPEG
    assert second.cached is True
    assert len(upstream.calls) == 1, "the second request went to the network"


def test_a_cached_tile_survives_a_new_cache_object(tmp_path, upstream):
    """Disk, not memory: restarting the API must not re-fetch the session's basemap."""
    TileCache(tmp_path / "tiles").get(15, 3, 4)
    reopened = TileCache(tmp_path / "tiles").get(15, 3, 4)

    assert reopened.cached is True
    assert len(upstream.calls) == 1


def test_it_asks_esri_for_z_y_x_and_not_z_x_y(cache, upstream):
    """Esri's path order is z/y/x.

    Swapping the two yields a perfectly valid tile of the wrong piece of the planet, which
    renders as a plausible coastline somewhere else entirely. Worth a test of its own.
    """
    cache.get(14, 8001, 6002)

    assert upstream.calls[0].endswith("/14/6002/8001")


# -- offline, which is a state and not an error ------------------------------------------


def test_an_uncached_tile_with_no_network_raises_rather_than_inventing_one(tmp_path, monkeypatch):
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream(fail=True))

    with pytest.raises(TileError):
        TileCache(tmp_path / "tiles").get(16, 1, 1)


def test_a_cached_tile_is_served_with_no_network_at_all(tmp_path, monkeypatch):
    """The requirement, stated as a test: once fetched, the map never needs the internet."""
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream())
    TileCache(tmp_path / "tiles").get(16, 1, 1)

    monkeypatch.setattr("surf.basemap.httpx.get", Upstream(fail=True))
    offline = TileCache(tmp_path / "tiles").get(16, 1, 1)

    assert offline.data == JPEG
    assert offline.cached is True


def test_an_empty_response_is_refused_rather_than_cached(tmp_path, monkeypatch):
    """A zero-byte tile stored once would be served forever, and would look like a bug in
    the renderer rather than in the cache."""
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream(data=b""))
    cache = TileCache(tmp_path / "tiles")

    with pytest.raises(TileError):
        cache.get(16, 1, 1)
    assert cache.count() == 0


# -- what is not a tile ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("z", "x", "y"),
    [
        (MIN_ZOOM - 1, 0, 0),
        (MAX_ZOOM + 1, 0, 0),
        (16, -1, 0),
        (16, 0, -1),
        (2, 4, 0),  # at zoom 2 the world is 4x4, so index 4 does not exist
        (16, 1 << 16, 0),
    ],
)
def test_an_impossible_tile_is_refused_before_the_network(cache, upstream, z, x, y):
    with pytest.raises(TileError):
        cache.get(z, x, y)
    assert upstream.calls == [], "an impossible tile was forwarded upstream"


def test_a_negative_index_cannot_escape_the_cache_directory(cache, upstream):
    """The path is built from these integers, so an unchecked one is a path traversal."""
    with pytest.raises(TileError):
        cache.get(16, -5, -5)
    assert cache.count() == 0


# -- what the client is told -------------------------------------------------------------


def test_the_attribution_is_not_empty():
    """Required by the imagery licence. A blank string here is a licence breach on screen."""
    assert ATTRIBUTION
    assert "Esri" in ATTRIBUTION


def test_the_endpoint_serves_a_tile_and_says_it_is_immutable(client, monkeypatch):
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream())

    response = client.get("/basemap/16/100/200")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert "immutable" in response.headers["cache-control"]
    assert response.content == JPEG


def test_the_endpoint_404s_offline_rather_than_500ing(client, monkeypatch):
    """Offline is a designed state: the UI draws its warm grid and the track still renders.

    A 500 would land in the diagnostics buffer as a defect and would be a lie -- nothing
    failed, there was simply no network, which this app is required to survive.
    """
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream(fail=True))

    assert client.get("/basemap/16/100/200").status_code == 404


def test_the_endpoint_refuses_an_impossible_tile(client, monkeypatch):
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream())

    assert client.get(f"/basemap/{MAX_ZOOM + 1}/1/1").status_code == 404


def test_the_info_endpoint_carries_everything_the_map_needs(client):
    body = client.get("/basemap").json()

    assert body["attribution"] == ATTRIBUTION
    assert "{z}" in body["tile_url"] and "{x}" in body["tile_url"] and "{y}" in body["tile_url"]
    assert body["min_zoom"] == MIN_ZOOM
    assert body["max_zoom"] == MAX_ZOOM


def test_a_tile_is_served_with_no_session_stored_at_all(client, monkeypatch):
    """A tile is addressed by z/x/y and nothing else.

    The `client` fixture holds an empty store, so this passing is the evidence: the basemap
    route never touches an activity, never learns an id, and cannot become a location lookup
    with extra steps. That matters because this repo is public and the session's coordinates
    are the one thing that must never reach it.
    """
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream())

    assert client.get("/activities").json() == []
    assert client.get("/basemap/16/100/200").status_code == 200
