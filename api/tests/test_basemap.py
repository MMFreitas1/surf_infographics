"""The basemap layers: fetched once, then served from disk forever.

The property that matters is the one `architecture.md` section 7 asks for — **a session
opens with no network** — so most of what follows is about the second request, not the
first, and about what happens when upstream is simply not there.

Since ADR-0019 there is more than one layer, and the tests that matter most are the ones
about keeping them apart: two sources at the same z/x/y are the same three integers, and a
cache that cannot tell them apart serves bathymetry as imagery, silently and forever.

Every test here runs offline. `httpx.get` is replaced rather than reached; a test suite that
quietly fetches from Esri or EMODnet would pass on this laptop and fail in CI, which is the
failure mode the rule in CLAUDE.md exists to prevent.
"""

from pathlib import Path

import httpx
import pytest

from surf.basemap import DEFAULT_LAYERS, LAYERS, Layer, TileCache, TileError

JPEG = b"\xff\xd8\xff\xe0 pretend this is imagery \xff\xd9"
PNG = b"\x89PNG\r\n\x1a\n pretend this is the sea floor"

IMAGERY = LAYERS["imagery"]
OCEAN = LAYERS["ocean"]


class Upstream:
    """A stand-in for a tile service that counts how often it was asked."""

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
    first = cache.get(IMAGERY, 16, 100, 200)
    second = cache.get(IMAGERY, 16, 100, 200)

    assert first.data == JPEG
    assert first.cached is False
    assert second.data == JPEG
    assert second.cached is True
    assert len(upstream.calls) == 1, "the second request went to the network"


def test_a_cached_tile_survives_a_new_cache_object(tmp_path, upstream):
    """Disk, not memory: restarting the API must not re-fetch the session's basemap."""
    TileCache(tmp_path / "tiles").get(IMAGERY, 15, 3, 4)
    reopened = TileCache(tmp_path / "tiles").get(IMAGERY, 15, 3, 4)

    assert reopened.cached is True
    assert len(upstream.calls) == 1


def test_it_asks_esri_for_z_y_x_and_not_z_x_y(cache, upstream):
    """Esri's path order is z/y/x.

    Swapping the two yields a perfectly valid tile of the wrong piece of the planet, which
    renders as a plausible coastline somewhere else entirely. Worth a test of its own.
    """
    cache.get(IMAGERY, 14, 8001, 6002)

    assert upstream.calls[0].endswith("/14/6002/8001")


def test_it_asks_emodnet_for_z_x_y_in_its_own_order(cache, upstream):
    """And EMODnet's order is the ordinary one, which is exactly why order is per layer."""
    cache.get(OCEAN, 10, 491, 389)

    assert upstream.calls[0].endswith("/10/491/389.png")


# -- keeping the layers apart ------------------------------------------------------------


def test_one_layers_tile_is_never_served_for_another(tmp_path, monkeypatch):
    """The same z/x/y names a different picture in every layer.

    A cache keyed on the three integers alone would answer the ocean request with the
    imagery tile it already had -- the sea floor rendered as a beach, with nothing on
    screen to suggest anything went wrong.
    """
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream(data=JPEG))
    cache = TileCache(tmp_path / "tiles")
    cache.get(IMAGERY, 10, 5, 6)

    monkeypatch.setattr("surf.basemap.httpx.get", (ocean := Upstream(data=PNG)))
    tile = cache.get(OCEAN, 10, 5, 6)

    assert tile.data == PNG
    assert tile.cached is False, "the imagery tile was served as bathymetry"
    assert len(ocean.calls) == 1


def test_each_layer_keeps_its_own_format_on_disk(cache, monkeypatch):
    """The layers do not agree on a format, so the extension travels with the layer."""
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream(data=PNG))
    cache.get(OCEAN, 10, 5, 6)

    assert cache.path_for(OCEAN, 10, 5, 6).suffix == ".png"
    assert cache.path_for(IMAGERY, 10, 5, 6).suffix == ".jpg"
    assert cache.count() == 1


def test_every_layer_declares_an_attribution_and_a_zoom_range():
    """Attribution is a licence condition. A blank string here is a breach on screen."""
    for layer in LAYERS.values():
        assert layer.attribution, f"{layer.id} has no attribution"
        assert layer.min_zoom <= layer.max_zoom
        assert layer.media_type and layer.extension


def test_the_layers_that_open_ticked_are_layers_that_exist():
    """And the sea floor is one of them: it is the base, even when the imagery covers it."""
    assert DEFAULT_LAYERS
    assert set(LAYERS) >= DEFAULT_LAYERS
    assert "ocean" in DEFAULT_LAYERS


# -- offline, which is a state and not an error ------------------------------------------


def test_an_uncached_tile_with_no_network_raises_rather_than_inventing_one(tmp_path, monkeypatch):
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream(fail=True))

    with pytest.raises(TileError):
        TileCache(tmp_path / "tiles").get(IMAGERY, 16, 1, 1)


def test_a_cached_tile_is_served_with_no_network_at_all(tmp_path, monkeypatch):
    """The requirement, stated as a test: once fetched, the map never needs the internet."""
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream())
    TileCache(tmp_path / "tiles").get(IMAGERY, 16, 1, 1)

    monkeypatch.setattr("surf.basemap.httpx.get", Upstream(fail=True))
    offline = TileCache(tmp_path / "tiles").get(IMAGERY, 16, 1, 1)

    assert offline.data == JPEG
    assert offline.cached is True


def test_an_empty_response_is_refused_rather_than_cached(tmp_path, monkeypatch):
    """A zero-byte tile stored once would be served forever, and would look like a bug in
    the renderer rather than in the cache."""
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream(data=b""))
    cache = TileCache(tmp_path / "tiles")

    with pytest.raises(TileError):
        cache.get(IMAGERY, 16, 1, 1)
    assert cache.count() == 0


def test_a_pre_rendered_layer_never_reaches_for_the_network(cache, upstream):
    """`local` is how a layer stops depending on anybody.

    A miss is the whole answer -- falling back to a fetch would quietly reintroduce the
    dependency the mode exists to remove, and it would work on this laptop.
    """
    ours = Layer(
        id="imagery-local",
        url="",
        attribution="ours",
        min_zoom=0,
        max_zoom=19,
        media_type="image/jpeg",
        extension="jpg",
        source="local",
    )

    with pytest.raises(TileError):
        cache.get(ours, 16, 1, 1)
    assert upstream.calls == [], "a pre-rendered layer went to the network"


# -- what is not a tile ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("z", "x", "y"),
    [
        (IMAGERY.min_zoom - 1, 0, 0),
        (IMAGERY.max_zoom + 1, 0, 0),
        (16, -1, 0),
        (16, 0, -1),
        (2, 4, 0),  # at zoom 2 the world is 4x4, so index 4 does not exist
        (16, 1 << 16, 0),
    ],
)
def test_an_impossible_tile_is_refused_before_the_network(cache, upstream, z, x, y):
    with pytest.raises(TileError):
        cache.get(IMAGERY, z, x, y)
    assert upstream.calls == [], "an impossible tile was forwarded upstream"


def test_a_zoom_past_a_layers_own_ceiling_is_refused(cache, upstream):
    """The ocean grid runs out long before the imagery does, and the map overzooms the last
    tile rather than asking for one that was never rendered."""
    with pytest.raises(TileError):
        cache.get(OCEAN, OCEAN.max_zoom + 1, 1, 1)
    assert cache.get(IMAGERY, OCEAN.max_zoom + 1, 1, 1).data == JPEG


def test_a_negative_index_cannot_escape_the_cache_directory(cache, upstream):
    """The path is built from these integers, so an unchecked one is a path traversal."""
    with pytest.raises(TileError):
        cache.get(IMAGERY, 16, -5, -5)
    assert cache.count() == 0


# -- what the client is told -------------------------------------------------------------


def test_the_endpoint_serves_a_tile_and_says_it_is_immutable(client, monkeypatch):
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream())

    response = client.get("/basemap/imagery/16/100/200")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert "immutable" in response.headers["cache-control"]
    assert response.content == JPEG


def test_the_endpoint_serves_each_layer_with_its_own_media_type(client, monkeypatch):
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream(data=PNG))

    response = client.get("/basemap/ocean/10/5/6")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_an_unknown_layer_is_a_404_before_any_network_call(client, upstream):
    assert client.get("/basemap/no-such-layer/16/100/200").status_code == 404
    assert upstream.calls == []


def test_the_endpoint_404s_offline_rather_than_500ing(client, monkeypatch):
    """Offline is a designed state: the UI draws its warm grid and the track still renders.

    A 500 would land in the diagnostics buffer as a defect and would be a lie -- nothing
    failed, there was simply no network, which this app is required to survive.
    """
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream(fail=True))

    assert client.get("/basemap/imagery/16/100/200").status_code == 404


def test_the_endpoint_refuses_an_impossible_tile(client, monkeypatch):
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream())

    assert client.get(f"/basemap/imagery/{IMAGERY.max_zoom + 1}/1/1").status_code == 404


def test_the_info_endpoint_carries_everything_the_map_needs(client):
    body = client.get("/basemap").json()
    layers = {layer["id"]: layer for layer in body["layers"]}

    assert set(layers) == set(LAYERS)
    for layer_id, served in layers.items():
        assert served["attribution"] == LAYERS[layer_id].attribution
        assert served["tile_url"] == f"/basemap/{layer_id}/{{z}}/{{x}}/{{y}}"
        assert served["min_zoom"] == LAYERS[layer_id].min_zoom
        assert served["max_zoom"] == LAYERS[layer_id].max_zoom

    defaults = {layer["id"] for layer in body["layers"] if layer["default"]}
    assert defaults == DEFAULT_LAYERS, "the map opened with the wrong layers ticked"


def test_a_tile_is_served_with_no_session_stored_at_all(client, monkeypatch):
    """A tile is addressed by layer and z/x/y and nothing else.

    The `client` fixture holds an empty store, so this passing is the evidence: the basemap
    route never touches an activity, never learns an id, and cannot become a location lookup
    with extra steps. That matters because this repo is public and the session's coordinates
    are the one thing that must never reach it.
    """
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream())

    assert client.get("/activities").json() == []
    assert client.get("/basemap/imagery/16/100/200").status_code == 200
