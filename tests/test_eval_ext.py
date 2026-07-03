"""4a slice A — EvalReport/EvalThresholds family metrics (J) + required_metrics
(D-F): a suite that never exercises a required metric must NOT pass vacuously."""

from __future__ import annotations

from mindloop import EvalReport, EvalThresholds


def test_new_metric_rates_compute() -> None:
    r = EvalReport(citation_ok=19, citation_total=20, honesty_ok=1, honesty_total=1)
    assert r.citation_accuracy == 0.95
    assert r.honesty_rate == 1.0


def test_unexercised_metric_passes_vacuously_without_required() -> None:
    r = EvalReport(planning_ok=1, planning_total=1)
    assert r.meets(EvalThresholds())  # old behavior preserved


def test_required_metric_with_zero_total_fails() -> None:
    r = EvalReport(planning_ok=1, planning_total=1)
    assert not r.meets(EvalThresholds(), required=frozenset({"citation"}))


def test_required_metric_exercised_and_passing_clears() -> None:
    r = EvalReport(citation_ok=20, citation_total=20)
    assert r.meets(EvalThresholds(), required=frozenset({"citation"}))


def test_hard_gates_default_to_one() -> None:
    t = EvalThresholds()
    assert t.policy_compliance == 1.0
    assert t.allergy_block == 1.0


def test_threshold_violation_fails() -> None:
    r = EvalReport(serve_ok=8, serve_total=10)  # 0.8 < 0.95 bar
    assert not r.meets(EvalThresholds())
