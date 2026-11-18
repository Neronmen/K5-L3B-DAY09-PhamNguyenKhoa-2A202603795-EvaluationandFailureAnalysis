"""Regression test from docs/trace_case.md: seeded_regression C-014@11 (FM-05 pre_deducted)."""
import pytest

pytestmark = pytest.mark.student


def _ctx(trial, label):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def test_lab9_c014_pre_deducted_caught_and_fixed_passes():
    from lab9.graders import QuoteKept, RefundAmountCorrect, ReplyMatchesLedger
    from lab9.trace_case import investigate

    bad, good = investigate("seeded_regression", "C-014", 11), investigate("fixed", "C-014", 11)
    for grader in (RefundAmountCorrect(), ReplyMatchesLedger(), QuoteKept()):
        assert grader.evaluate(_ctx(bad["trial"], bad["label"])).value is False, type(grader).__name__
        assert grader.evaluate(_ctx(good["trial"], good["label"])).value is True, type(grader).__name__
    kinds = [e["kind"] for e in bad["trial"]["events"]]
    assert kinds.index("refund_history") < kinds.index("proposal")   # first wrong step: event 5
