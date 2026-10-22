"""The basemap layers: fetched once, then served from disk forever.

The property that matters is the one `architecture.md` section 7 asks for — **a session
opens with no network** — so most of what follows is about the second request, not the
first, and about what happens when upstream is simply not there.

Since ADR-0019 there is more than one layer, and the tests that matter most are the ones
about keeping them apart: two sources at the same z/x/y are the same three integers, and a
cache that cannot tell them apart serves bathymetry as imagery, silently and forever.

Every test here runs offline. `httpx.get` is replaced rather than reached; a test suite that
quietly fetches from DGT or EMODnet would pass on this laptop and fail in CI, which is the
failure mode the rule in CLAUDE.md exists to prevent.
"""

from pathlib import Path

import httpx
import pytest

from surf.basemap import (
    DEFAULT_LAYERS,
    LAYERS,
    Layer,
    TileCache,
    TileError,
    _mercator_bbox,
)

JPEG = b"\xff\xd8\xff\xe0 pretend this is imagery \xff\xd9"
PNG = b"\x89PNG\r\n\x1a\n pretend this is the sea floor"

IMAGERY = LAYERS["imagery"]
OCEAN = LAYERS["ocean"]

# Tiles inside the imagery layer's declared coverage, since a national service refuses the
# rest. Derived from the middle of DGT's own published bounding box -- never from a session,
# because this repo is public and a session is somebody's address at a time of day.
PT10 = (10, 489, 389)
PT14 = (14, 7830, 6230)
PT16 = (16, 31320, 24923)
PT17 = (17, 62640, 49846)


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
    first = cache.get(IMAGERY, *PT16)
    second = cache.get(IMAGERY, *PT16)

    assert first.data == JPEG
    assert first.cached is False
    assert second.data == JPEG
    assert second.cached is True
    assert len(upstream.calls) == 1, "the second request went to the network"


def test_a_cached_tile_survives_a_new_cache_object(tmp_path, upstream):
    """Disk, not memory: restarting the API must not re-fetch the session's basemap."""
    TileCache(tmp_path / "tiles").get(IMAGERY, *PT16)
    reopened = TileCache(tmp_path / "tiles").get(IMAGERY, *PT16)

    assert reopened.cached is True
    assert len(upstream.calls) == 1


@pytest.mark.parametrize(
    ("z", "x", "y", "expected"),
    [
        # The whole world, which is the one tile whose answer anybody can check by eye.
        (0, 0, 0, "-20037508.343,-20037508.343,20037508.343,20037508.343"),
        # y counts down from the north, so 1/1/0 is the north-east quadrant and 1/0/1 the
        # south-west. Getting that upside down is the classic way to draw a valid tile of
        # the wrong hemisphere.
        (1, 1, 0, "0.000,0.000,20037508.343,20037508.343"),
        (1, 0, 1, "-20037508.343,-20037508.343,0.000,0.000"),
    ],
)
def test_a_tile_index_becomes_the_bounding_box_it_names(z, x, y, expected):
    """A WMS answers a box, so the transform is load-bearing and has a known answer."""
    assert _mercator_bbox(z, x, y) == expected


def test_a_bounding_box_layer_is_asked_for_a_box_and_not_a_path(cache, upstream):
    """DGT serves WMS: the tile index goes into the query, not into the path.

    The imagery layer's template spells ``{bbox}`` where the ocean's spells ``{z}/{x}/{y}``,
    and asking the wrong one of those two questions yields no tile at all -- which at least
    fails loudly, unlike every other way of getting a tile address wrong.
    """
    cache.get(IMAGERY, *PT14)

    called = upstream.calls[0]
    assert f"bbox={_mercator_bbox(*PT14)}" in called
    assert "{bbox}" not in called, "the template was sent unformatted"
    assert "/14/7830/6230" not in called


def test_the_imagery_layer_is_open_data_we_may_cache_forever():
    """The point of ADR-0021: this module keeps tiles, so the licence has to allow it.

    Esri's did not. A silent return to a host whose terms restrict caching would re-break a
    decision that was made for licensing reasons and cannot be seen on screen.
    """
    assert "dgterritorio.gov.pt" in IMAGERY.url
    assert "Direção-Geral do Território" in IMAGERY.attribution
    assert "CC BY 4.0" in IMAGERY.attribution


def test_changing_the_provider_behind_a_role_does_not_inherit_its_tiles(tmp_path):
    """A role outlives its provider; the tiles on disk do not.

    Keyed on the role alone, the previous provider's imagery would be served as the new
    one's -- a different picture of the same three integers, with nothing on screen to say
    so. The directory carries the provider, so the old tiles are simply not found.
    """
    previous = Layer(
        id="imagery",
        url="https://example.invalid/{z}/{y}/{x}",
        attribution="the provider that came before",
        min_zoom=0,
        max_zoom=19,
        media_type="image/jpeg",
        extension="jpg",
    )

    assert previous.storage_id != IMAGERY.storage_id
    cache = TileCache(tmp_path / "tiles")
    assert cache.path_for(previous, 14, 1, 2) != cache.path_for(IMAGERY, 14, 1, 2)


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
    cache.get(IMAGERY, *PT10)

    monkeypatch.setattr("surf.basemap.httpx.get", (ocean := Upstream(data=PNG)))
    tile = cache.get(OCEAN, *PT10)

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
        TileCache(tmp_path / "tiles").get(IMAGERY, *PT16)


def test_a_cached_tile_is_served_with_no_network_at_all(tmp_path, monkeypatch):
    """The requirement, stated as a test: once fetched, the map never needs the internet."""
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream())
    TileCache(tmp_path / "tiles").get(IMAGERY, *PT16)

    monkeypatch.setattr("surf.basemap.httpx.get", Upstream(fail=True))
    offline = TileCache(tmp_path / "tiles").get(IMAGERY, *PT16)

    assert offline.data == JPEG
    assert offline.cached is True


def test_an_empty_response_is_refused_rather_than_cached(tmp_path, monkeypatch):
    """A zero-byte tile stored once would be served forever, and would look like a bug in
    the renderer rather than in the cache."""
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream(data=b""))
    cache = TileCache(tmp_path / "tiles")

    with pytest.raises(TileError):
        cache.get(IMAGERY, *PT16)
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
    assert cache.get(IMAGERY, *PT17).data == JPEG


def test_a_tile_outside_a_layers_coverage_is_refused_rather_than_cached_blank(cache, upstream):
    """A national service does not say "I do not have that".

    Asked for ground it does not hold, DGT answers 200 with a valid, uniform JPEG. Fetched
    once and kept, that is a white square served forever -- indistinguishable on screen
    from imagery of a very calm, very pale sea. So coverage is declared and checked here,
    and the tile never leaves for the network at all.
    """
    assert IMAGERY.bounds is not None

    # Hossegor is a surf town, and it is not in Portugal.
    with pytest.raises(TileError):
        cache.get(IMAGERY, 14, 8120, 5880)

    assert upstream.calls == [], "a tile outside coverage was fetched"
    assert cache.count() == 0


def test_a_layer_without_declared_coverage_is_asked_anywhere(cache, upstream):
    """The sea floor is global, so `bounds=None` must not become a silent refusal."""
    assert OCEAN.bounds is None
    assert cache.get(OCEAN, 10, 1, 1).data is not None


def test_a_negative_index_cannot_escape_the_cache_directory(cache, upstream):
    """The path is built from these integers, so an unchecked one is a path traversal."""
    with pytest.raises(TileError):
        cache.get(IMAGERY, 16, -5, -5)
    assert cache.count() == 0


# -- what the client is told -------------------------------------------------------------


def test_the_endpoint_serves_a_tile_and_says_it_is_immutable(client, monkeypatch):
    monkeypatch.setattr("surf.basemap.httpx.get", Upstream())

    response = client.get("/basemap/imagery/16/31320/24923")

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

    assert client.get("/basemap/imagery/16/31320/24923").status_code == 404


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
    assert client.get("/basemap/imagery/16/31320/24923").status_code == 200
