"""The model saturates RAM only while in use (Phase 8 contract, tested now)."""

from surf.llm.lifecycle import LlmLifecycle

MODEL = "qwen2.5:7b-instruct-q4_K_M"


def _mgr(backend, clock, ttl=600.0):
    return LlmLifecycle(backend=backend, model=MODEL, idle_ttl_seconds=ttl, clock=clock)


def test_model_is_not_loaded_until_first_use(fake_backend, fake_clock):
    _mgr(fake_backend, fake_clock)
    assert fake_backend.loads == 0
    assert fake_backend.is_loaded(MODEL) is False


def test_acquire_loads_once_and_reuses(fake_backend, fake_clock):
    mgr = _mgr(fake_backend, fake_clock)
    with mgr.acquire():
        pass
    with mgr.acquire():
        pass
    assert fake_backend.loads == 1


def test_unloads_after_idle_ttl(fake_backend, fake_clock):
    mgr = _mgr(fake_backend, fake_clock, ttl=600.0)
    with mgr.acquire():
        pass
    fake_clock.advance(599.0)
    assert mgr.tick() is False
    assert fake_backend.is_loaded(MODEL) is True
    fake_clock.advance(2.0)
    assert mgr.tick() is True
    assert fake_backend.is_loaded(MODEL) is False


def test_never_unloads_while_work_is_in_flight(fake_backend, fake_clock):
    mgr = _mgr(fake_backend, fake_clock, ttl=1.0)
    with mgr.acquire():
        fake_clock.advance(10_000.0)
        assert mgr.tick() is False
        assert mgr.unload_now() is False
        assert fake_backend.is_loaded(MODEL) is True
    # the idle countdown restarts when the work finishes, not when it started
    assert mgr.tick() is False
    fake_clock.advance(2.0)
    assert mgr.tick() is True


def test_manual_unload_is_immediate(fake_backend, fake_clock):
    mgr = _mgr(fake_backend, fake_clock, ttl=99_999.0)
    with mgr.acquire():
        pass
    assert mgr.unload_now() is True
    assert fake_backend.is_loaded(MODEL) is False


def test_unload_now_on_an_unloaded_model_is_a_noop(fake_backend, fake_clock):
    mgr = _mgr(fake_backend, fake_clock)
    assert mgr.unload_now() is False
    assert fake_backend.unloads == 0


def test_status_reports_countdown_to_unload(fake_backend, fake_clock):
    mgr = _mgr(fake_backend, fake_clock, ttl=600.0)
    with mgr.acquire():
        assert mgr.status().unloads_in_seconds is None
    fake_clock.advance(100.0)
    st = mgr.status()
    assert st.loaded is True
    assert st.in_use == 0
    assert st.unloads_in_seconds == 500.0


def test_reload_after_unload(fake_backend, fake_clock):
    mgr = _mgr(fake_backend, fake_clock, ttl=1.0)
    with mgr.acquire():
        pass
    fake_clock.advance(5.0)
    assert mgr.tick() is True
    with mgr.acquire():
        pass
    assert fake_backend.loads == 2
    assert fake_backend.is_loaded(MODEL) is True
