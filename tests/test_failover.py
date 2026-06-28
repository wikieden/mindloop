"""P7.1 — FailoverVerbalizer: remote → on-body LLM failover (network-free)."""

from __future__ import annotations

import pytest
from tempomem import QueryError

from mindloop import FailoverVerbalizer, VerbalizerReasoner


class _Ok:
    """A backend that always succeeds, tagging its output."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        return f"{self.tag}:{prompt}"


class _Dead:
    """A backend whose transport is always down."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        raise QueryError("transport down")


class _Flaky:
    """Fails its first `fail_n` calls (QueryError), then succeeds."""

    def __init__(self, fail_n: int) -> None:
        self.fail_n = fail_n
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        if self.calls <= self.fail_n:
            raise QueryError("flaky")
        return f"ok:{prompt}"


def test_primary_serves_when_healthy() -> None:
    primary, fb = _Ok("remote"), _Ok("onbody")
    fv = FailoverVerbalizer([primary, fb])
    assert fv.complete("hi") == "remote:hi"
    assert fv.mode == "primary"
    assert fv.active_index == 0
    assert fb.calls == 0  # fallback never touched


def test_fails_over_to_onbody() -> None:
    fb = _Ok("onbody")
    fv = FailoverVerbalizer([_Dead(), fb])
    assert fv.complete("hi") == "onbody:hi"
    assert fv.mode == "fallback"
    assert fv.active_index == 1


def test_cooldown_demotes_primary_then_recovers() -> None:
    primary, fb = _Flaky(fail_n=1), _Ok("onbody")
    fv = FailoverVerbalizer([primary, fb], cooldown=2)

    # call 1: primary fails -> fallback serves, primary put on a 2-call cooldown
    assert fv.complete("a") == "onbody:a"
    assert fv.mode == "fallback"
    assert primary.calls == 1

    # calls 2-3: primary demoted (tried last); fallback serves; primary not retried
    assert fv.complete("b") == "onbody:b"
    assert fv.complete("c") == "onbody:c"
    assert primary.calls == 1  # primary was NOT called during cooldown

    # call 4: cooldown expired -> primary retried, now healthy -> back to primary
    assert fv.complete("d") == "ok:d"
    assert fv.mode == "primary"
    assert primary.calls == 2


def test_primary_is_last_resort_during_cooldown() -> None:
    # cooling, but every fallback is also down -> primary is still tried last
    primary, fb = _Flaky(fail_n=1), _Dead()
    fv = FailoverVerbalizer([primary, fb], cooldown=5)
    with pytest.raises(QueryError):
        fv.complete("a")  # both down on the first call
    # primary now healthy; even while cooling, it serves as last resort
    assert fv.complete("b") == "ok:b"


def test_all_backends_down_raises() -> None:
    fv = FailoverVerbalizer([_Dead(), _Dead()])
    with pytest.raises(QueryError, match="all 2 verbalizer backends failed"):
        fv.complete("hi")


def test_on_switch_fires_on_change() -> None:
    switches: list[tuple[int, int, str]] = []
    fv = FailoverVerbalizer(
        [_Flaky(fail_n=1), _Ok("onbody")],
        cooldown=0,
        on_switch=lambda a, b, r: switches.append((a, b, r)),
    )
    fv.complete("a")  # primary fails -> fallback (0->1, failover)
    fv.complete("b")  # primary healthy -> primary (1->0, recovered)
    assert switches == [(0, 1, "failover"), (1, 0, "recovered")]


def test_empty_backends_rejected() -> None:
    with pytest.raises(ValueError, match="at least one backend"):
        FailoverVerbalizer([])


def test_wraps_into_reasoner_unchanged() -> None:
    # the brain seam is unchanged: a Reasoner backed by a failover verbalizer
    # answers via the on-body fallback when the remote is down
    fv = FailoverVerbalizer([_Dead(), _Ok("onbody")])
    reasoner = VerbalizerReasoner(fv)
    answer = reasoner.reason("what is here?", "SCENE: a bottle [#1]")
    assert "onbody" in answer.text
