"""The pipeline spine: does data actually flow through a cached stage, end to end.

Phase 0 defined the `Stage` protocol and a `StageCache`, but nothing implemented one and
the cache was only ever exercised on `b"payload"` literals. This file is where that stops
being a claim. It runs a real activity file through L0 and asserts the three things the
whole content-addressed design rests on:

* a first run does the work and stores it, a second run reuses it;
* a cache hit returns *exactly* what the run returned, samples and session alike;
* changing a param that changes the output changes the key, so a stale payload can never
  be served under a new rule.

As L1 lands it is added here rather than getting a spine argument of its own.
"""

import json
from dataclasses import dataclass

import pytest

from fit_builder import (
    BASE_UINT32,
    data_message,
    definition_message,
    fit_file,
    record_fields,
    record_payload,
    small_fit,
)
from surf.ingest import parse_activity
from surf.ingest.stage import (
    CODE_VERSION,
    NAME,
    IngestStage,
    PayloadError,
    decode_activity,
    encode_activity,
    samples_from_parquet,
)
from surf.models import BlindCause, Sample
from surf.pipeline import Stage, StageCache, StageMeta, run_stage, stage_key

NOT_AN_ACTIVITY = b"this is not a FIT file and parsing it would raise"
"""Handed to a stage that must not run. A cache hit is proved by this never being parsed."""

DIGEST = "a" * 64


def gapped_fit(*, stamps=(1_000_000, 1_000_001, 1_000_005)):
    """A positioned FIT with a hole in it, so gap tolerance has something to decide."""
    file_id = [(1, 2, 4), (2, 2, 4), (3, 4, BASE_UINT32), (4, 4, BASE_UINT32)]
    body = definition_message(2, 0, file_id)
    body += data_message(2, b"\x01\x00\xdb\x0c\x2a\x00\x00\x00\x40\x42\x0f\x00")
    body += definition_message(3, 18, [(5, 1, 0)])
    body += data_message(3, bytes([38]))
    body += definition_message(0, 20, record_fields())
    for stamp in stamps:
        body += data_message(
            0,
            record_payload(
                stamp,
                lat=int(10.0 / (180.0 / 2**31)),
                lon=int(20.0 / (180.0 / 2**31)),
                heart_rate=100,
                speed_mms=1500,
            ),
        )
    return fit_file(body)


@dataclass(frozen=True)
class Doubling:
    """A toy stage. Exercises the runner without dragging a parser into it."""

    factor: int = 2

    @property
    def meta(self) -> StageMeta:
        return StageMeta(name="test", code_version="1", params={"factor": self.factor})

    def run(self, data: list[int]) -> list[int]:
        return [value * self.factor for value in data]

    def encode(self, output: list[int]) -> bytes:
        return json.dumps(output).encode("utf-8")

    def decode(self, payload: bytes) -> list[int]:
        return json.loads(payload)


# --------------------------------------------------------------------------- the runner


def test_a_stage_implementation_satisfies_the_protocol():
    assert isinstance(Doubling(), Stage)
    assert isinstance(IngestStage(), Stage)


def test_the_first_run_works_and_the_second_is_served_from_the_cache(tmp_path):
    cache = StageCache(tmp_path)
    first = run_stage(Doubling(), cache, input_hash=DIGEST, data=[1, 2, 3])
    second = run_stage(Doubling(), cache, input_hash=DIGEST, data=[1, 2, 3])

    assert first.cached is False
    assert second.cached is True
    assert first.output == second.output == [2, 4, 6]
    assert first.key == second.key


def test_a_changed_param_lands_in_a_different_entry(tmp_path):
    cache = StageCache(tmp_path)
    doubled = run_stage(Doubling(factor=2), cache, input_hash=DIGEST, data=[1, 2, 3])
    tripled = run_stage(Doubling(factor=3), cache, input_hash=DIGEST, data=[1, 2, 3])

    assert doubled.key != tripled.key
    assert tripled.cached is False  # the old entry was not mistaken for this one
    assert tripled.output == [3, 6, 9]


def test_a_changed_input_lands_in_a_different_entry(tmp_path):
    cache = StageCache(tmp_path)
    one = run_stage(Doubling(), cache, input_hash="a" * 64, data=[1])
    two = run_stage(Doubling(), cache, input_hash="b" * 64, data=[9])
    assert one.key != two.key
    assert two.output == [18]


# ------------------------------------------------------------------------------- the L0 stage


def test_l0_is_named_and_versioned_by_the_stage_not_the_store():
    meta = IngestStage().meta
    assert meta.name == NAME == "L0"
    assert meta.code_version == CODE_VERSION


def test_the_filename_is_not_part_of_the_key(tmp_path):
    """Cosmetic metadata must not fork one session into two cache entries."""
    cache = StageCache(tmp_path)
    named = IngestStage(source_file="morning.fit")
    unnamed = IngestStage()
    assert stage_key(named, cache, DIGEST) == stage_key(unnamed, cache, DIGEST)


def test_gap_tolerance_is_part_of_the_key(tmp_path):
    cache = StageCache(tmp_path)
    strict = IngestStage(gap_tolerance=1.5)
    loose = IngestStage(gap_tolerance=10.0)
    assert stage_key(strict, cache, DIGEST) != stage_key(loose, cache, DIGEST)


def test_gap_tolerance_changes_the_windows_it_keys_on(tmp_path):
    """The param is real: the same bytes yield different blind windows under each rule."""
    cache = StageCache(tmp_path)
    data = gapped_fit()

    strict = run_stage(IngestStage(gap_tolerance=1.5), cache, input_hash=DIGEST, data=data)
    loose = run_stage(IngestStage(gap_tolerance=10.0), cache, input_hash=DIGEST, data=data)

    assert [w.cause for w in strict.output.blind_windows] == [BlindCause.MISSING_RECORD]
    assert loose.output.blind_windows == []


def test_a_file_runs_through_l0_and_the_second_pass_never_parses_it(tmp_path):
    """The spine, on a FIT: miss, store, hit.

    The second call is handed bytes that are not an activity at all. If the runner were
    quietly re-parsing rather than reading its cache, this would raise instead of
    returning the session.
    """
    cache = StageCache(tmp_path)
    stage = IngestStage(source_file="session.fit")

    first = run_stage(stage, cache, input_hash=DIGEST, data=small_fit())
    assert first.cached is False
    assert cache.get(NAME, first.key) is not None

    second = run_stage(stage, cache, input_hash=DIGEST, data=NOT_AN_ACTIVITY)
    assert second.cached is True
    assert second.output.model_dump() == first.output.model_dump()


def test_the_cached_payload_carries_the_whole_session_not_just_its_samples(tmp_path):
    """A hit must not need a database row to be complete."""
    activity = parse_activity(small_fit(), source_file="session.fit")
    restored = decode_activity(encode_activity(activity))
    assert restored.model_dump() == activity.model_dump()


def test_absent_measurements_round_trip_as_none_not_zero():
    """The invariant the payload format exists to protect.

    Parquet has a null and we use it. Writing 0.0 for a sample with no fix would turn
    "we could not see" into "the surfer was at the equator, stationary", and every
    coverage number downstream would quietly become a lie.
    """
    samples = [Sample(t=0.0, lat=10.0, lon=20.0, speed_ms=0.0), Sample(t=1.0)]
    activity = parse_activity(small_fit()).model_copy(update={"samples": samples})
    restored = samples_from_parquet(encode_activity(activity))

    assert restored[0].speed_ms == 0.0  # a real, measured zero survives as zero
    assert restored[1].lat is None
    assert restored[1].lon is None
    assert restored[1].speed_ms is None  # and an absence survives as an absence
    assert restored[1].hr_bpm is None
    assert restored[1].has_position is False


def test_a_payload_this_stage_did_not_write_is_refused(tmp_path):
    """Better a loud error than an activity silently invented from missing metadata."""
    activity = parse_activity(small_fit())
    stripped = encode_activity(activity)
    # A Parquet file with the right columns but no session metadata: the shape another
    # tool might produce. Decoding it as an Activity would be a guess.
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pq.read_table(pa.BufferReader(stripped)).replace_schema_metadata({})
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink)

    with pytest.raises(PayloadError, match="no session metadata"):
        decode_activity(bytes(sink.getvalue().to_pybytes()))


# ------------------------------------------------------- the same spine, on the real session


def test_the_reference_session_runs_through_l0_and_comes_back_identical(sample_fit, tmp_path):
    """3790 samples, half of them positionless, through Parquet and back unchanged."""
    cache = StageCache(tmp_path)
    stage = IngestStage(source_file=sample_fit.name)
    data = sample_fit.read_bytes()

    first = run_stage(stage, cache, input_hash=DIGEST, data=data)
    second = run_stage(stage, cache, input_hash=DIGEST, data=NOT_AN_ACTIVITY)

    assert first.cached is False
    assert second.cached is True
    assert second.output.model_dump() == first.output.model_dump()
    assert second.output.position_coverage == first.output.position_coverage
