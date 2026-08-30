"""The pipeline spine: does data actually flow through a cached stage, end to end.

Phase 0 defined the `Stage` protocol and a `StageCache`, but nothing implemented one and
the cache was only ever exercised on `b"payload"` literals. This file is where that stops
being a claim. It runs a real activity file through L0 and asserts the three things the
whole content-addressed design rests on:

* a first run does the work and stores it, a second run reuses it;
* a cache hit returns *exactly* what the run returned, samples and session alike;
* changing a param that changes the output changes the key, so a stale payload can never
  be served under a new rule.

L1, L2 and L3 are here too, each chained off the key below it rather than run in isolation,
so that invalidation propagating *down* the chain is also a thing one test can prove.
Later stages join the same file rather than getting a spine argument of their own.
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
from surf.pipeline.l1 import KinematicsStage
from surf.pipeline.l2 import FrameStage
from surf.pipeline.l3 import CandidateStage

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


# --------------------------------------------------------------- L0 -> L1, as a chain


class Exploded:
    """Passed as a stage's input when it must not run. Touching it is the failure."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"the stage ran instead of reading its cache (touched {name})")


def ingest_into(cache, *, gap_tolerance=1.5, data=None):
    """Run L0 and hand back its result, which is L1's input and input hash."""
    stage = IngestStage(gap_tolerance=gap_tolerance)
    return run_stage(stage, cache, input_hash=DIGEST, data=data or small_fit())


def test_l1_runs_off_l0s_output_and_the_second_pass_never_smooths_again(tmp_path):
    cache = StageCache(tmp_path)
    ingested = ingest_into(cache)
    stage = KinematicsStage()

    first = run_stage(stage, cache, input_hash=ingested.key, data=ingested.output)
    second = run_stage(stage, cache, input_hash=ingested.key, data=Exploded())

    assert first.cached is False
    assert second.cached is True
    assert [p.model_dump() for p in second.output] == [p.model_dump() for p in first.output]
    assert len(first.output) == len(ingested.output.samples)


def test_an_l1_param_lands_in_a_different_entry(tmp_path):
    cache = StageCache(tmp_path)
    ingested = ingest_into(cache)

    tight = run_stage(
        KinematicsStage(process_noise=0.05), cache, input_hash=ingested.key, data=ingested.output
    )
    loose = run_stage(
        KinematicsStage(process_noise=4.0), cache, input_hash=ingested.key, data=ingested.output
    )

    assert tight.key != loose.key
    assert loose.cached is False


def test_changing_an_l0_param_invalidates_l1_too(tmp_path):
    """The payoff of keying L1 on L0's key: a stale track cannot outlive its input.

    Nothing about L1 changed here. Its cache entry moves because the thing it was computed
    from moved, which is the property that makes a chain of caches safe to trust.
    """
    cache = StageCache(tmp_path)
    stage = KinematicsStage()

    strict = ingest_into(cache, gap_tolerance=1.5)
    loose = ingest_into(cache, gap_tolerance=10.0)
    assert strict.key != loose.key

    on_strict = run_stage(stage, cache, input_hash=strict.key, data=strict.output)
    on_loose = run_stage(stage, cache, input_hash=loose.key, data=loose.output)

    assert on_strict.key != on_loose.key
    assert on_loose.cached is False, "L1 must not serve a track built from other samples"


# --------------------------------------------------------------- L1 -> L2, as a chain


def smooth_into(cache, *, ingested, **params: float):
    """Run L1 off an L0 result and hand back what L2 needs: the output and its key."""
    return run_stage(
        KinematicsStage(**params), cache, input_hash=ingested.key, data=ingested.output
    )


def test_l2_runs_off_l1s_output_and_the_second_pass_never_re_estimates(tmp_path):
    cache = StageCache(tmp_path)
    smoothed = smooth_into(cache, ingested=ingest_into(cache))
    stage = FrameStage()

    first = run_stage(stage, cache, input_hash=smoothed.key, data=smoothed.output)
    second = run_stage(stage, cache, input_hash=smoothed.key, data=Exploded())

    assert first.cached is False
    assert second.cached is True
    assert [f.model_dump() for f in second.output.samples] == [
        f.model_dump() for f in first.output.samples
    ]


def test_a_cache_hit_returns_the_frame_and_not_just_the_rows(tmp_path):
    """L2's output is a frame *and* a track, and the frame lives in file metadata.

    That is the part a columnar round-trip is most likely to quietly drop, and dropping it
    would leave a cached session with a default bearing that reads exactly like a measured
    one.
    """
    cache = StageCache(tmp_path)
    smoothed = smooth_into(cache, ingested=ingest_into(cache))
    stage = FrameStage()

    first = run_stage(stage, cache, input_hash=smoothed.key, data=smoothed.output)
    second = run_stage(stage, cache, input_hash=smoothed.key, data=Exploded())

    assert second.output.frame == first.output.frame


def test_an_l2_param_lands_in_a_different_entry(tmp_path):
    cache = StageCache(tmp_path)
    smoothed = smooth_into(cache, ingested=ingest_into(cache))

    gentle = run_stage(
        FrameStage(speed_exponent=2.0), cache, input_hash=smoothed.key, data=smoothed.output
    )
    steep = run_stage(
        FrameStage(speed_exponent=6.0), cache, input_hash=smoothed.key, data=smoothed.output
    )

    assert gentle.key != steep.key
    assert steep.cached is False


def test_changing_an_l0_param_invalidates_l2_two_links_down(tmp_path):
    """The chain has to carry invalidation the whole way, not just one link.

    L2 is keyed on L1's key, which is keyed on L0's. Move the gap tolerance and the frame
    has to move with it, even though nothing in L1 or L2 changed.
    """
    cache = StageCache(tmp_path)
    stage = FrameStage()

    strict = smooth_into(cache, ingested=ingest_into(cache, gap_tolerance=1.5))
    loose = smooth_into(cache, ingested=ingest_into(cache, gap_tolerance=10.0))
    assert strict.key != loose.key

    on_strict = run_stage(stage, cache, input_hash=strict.key, data=strict.output)
    on_loose = run_stage(stage, cache, input_hash=loose.key, data=loose.output)

    assert on_strict.key != on_loose.key
    assert on_loose.cached is False, "L2 must not serve a frame built from another track"


# --------------------------------------------------------------- L2 -> L3, as a chain


def frame_into(cache, *, smoothed, **params: float):
    """Run L2 off an L1 result and hand back what L3 needs: the output and its key."""
    return run_stage(FrameStage(**params), cache, input_hash=smoothed.key, data=smoothed.output)


def test_l3_runs_off_l2s_output_and_the_second_pass_never_re_proposes(tmp_path):
    cache = StageCache(tmp_path)
    framed = frame_into(cache, smoothed=smooth_into(cache, ingested=ingest_into(cache)))
    stage = CandidateStage()

    first = run_stage(stage, cache, input_hash=framed.key, data=framed.output)
    second = run_stage(stage, cache, input_hash=framed.key, data=Exploded())

    assert first.cached is False
    assert second.cached is True
    assert second.output.frame == first.output.frame
    assert [c.model_dump() for c in second.output.candidates] == [
        c.model_dump() for c in first.output.candidates
    ]


def test_an_l3_param_lands_in_a_different_entry(tmp_path):
    cache = StageCache(tmp_path)
    framed = frame_into(cache, smoothed=smooth_into(cache, ingested=ingest_into(cache)))

    generous = run_stage(
        CandidateStage(quantile=0.60), cache, input_hash=framed.key, data=framed.output
    )
    strict = run_stage(
        CandidateStage(quantile=0.95), cache, input_hash=framed.key, data=framed.output
    )

    assert generous.key != strict.key
    assert strict.cached is False


def test_sweeping_an_l3_threshold_reuses_the_frame_beneath_it(tmp_path):
    """Why L2 and L3 are two stages at all (ADR-0011).

    Retuning candidate generation must not drag bearing estimation along with it. The L2
    entry is keyed on L1, not on anything L3 chose, so it is computed once and reused.
    """
    cache = StageCache(tmp_path)
    smoothed = smooth_into(cache, ingested=ingest_into(cache))

    first = frame_into(cache, smoothed=smoothed)
    for quantile in (0.60, 0.75, 0.95):
        again = frame_into(cache, smoothed=smoothed)
        assert again.cached is True, "the frame was re-estimated for a candidate sweep"
        assert again.key == first.key
        run_stage(CandidateStage(quantile=quantile), cache, input_hash=again.key, data=again.output)


def test_changing_an_l0_param_invalidates_l3_three_links_down(tmp_path):
    """Invalidation has to travel the whole chain, not just the link above."""
    cache = StageCache(tmp_path)
    stage = CandidateStage()

    strict = frame_into(
        cache, smoothed=smooth_into(cache, ingested=ingest_into(cache, gap_tolerance=1.5))
    )
    loose = frame_into(
        cache, smoothed=smooth_into(cache, ingested=ingest_into(cache, gap_tolerance=10.0))
    )
    assert strict.key != loose.key

    on_strict = run_stage(stage, cache, input_hash=strict.key, data=strict.output)
    on_loose = run_stage(stage, cache, input_hash=loose.key, data=loose.output)

    assert on_strict.key != on_loose.key
    assert on_loose.cached is False, "L3 must not serve candidates built from another frame"
