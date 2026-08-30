"""Stage cache is content-addressed: same inputs hit, changed params miss."""

from surf.pipeline import StageCache, content_hash


def test_hash_is_order_independent_for_mappings():
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})


def test_hash_changes_with_value():
    assert content_hash({"a": 1}) != content_hash({"a": 2})


def test_key_changes_when_params_change(tmp_path):
    cache = StageCache(tmp_path)
    base = {"input_hash": "abc", "code_version": "1"}
    k1 = cache.key(params={"threshold": 2.5}, **base)
    k2 = cache.key(params={"threshold": 2.6}, **base)
    assert k1 != k2


def test_key_changes_when_code_version_changes(tmp_path):
    cache = StageCache(tmp_path)
    k1 = cache.key(input_hash="abc", params={}, code_version="1")
    k2 = cache.key(input_hash="abc", params={}, code_version="2")
    assert k1 != k2


def test_roundtrip_and_miss(tmp_path):
    cache = StageCache(tmp_path)
    key = cache.key(input_hash="abc", params={"t": 1}, code_version="1")
    assert cache.get("L1", key) is None
    cache.put("L1", key, b"payload")
    assert cache.get("L1", key) == b"payload"
    assert cache.get("L2", key) is None


def test_put_is_atomic_leaving_no_tmp_file(tmp_path):
    cache = StageCache(tmp_path)
    key = cache.key(input_hash="abc", params={}, code_version="1")
    path = cache.put("L1", key, b"x")
    assert path.is_file()
    assert not list(path.parent.glob("*.tmp"))
