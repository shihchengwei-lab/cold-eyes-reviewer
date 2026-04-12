"""Tests for cold_eyes.retry.strategy."""

from cold_eyes.retry.strategy import select_strategy


def _brief(strategy="patch_localized_bug", retry_count=1, failed_gates=None):
    return {
        "retry_strategy": strategy,
        "retry_count": retry_count,
        "failed_gates": failed_gates or ["test_runner"],
    }


class TestSelectStrategy:
    def test_normal_retry(self):
        result = select_strategy(_brief())
        assert result["action"] == "retry"
        assert result["strategy"] == "patch_localized_bug"

    def test_abort_on_abort_strategy(self):
        result = select_strategy(_brief(strategy="abort_and_escalate"))
        assert result["action"] == "abort"

    def test_abort_on_high_retry_count(self):
        result = select_strategy(_brief(retry_count=4))
        assert result["action"] == "abort"

    def test_escalate_on_repeated_strategy(self):
        brief = _brief(strategy="patch_localized_bug")
        prev = [
            _brief(strategy="patch_localized_bug"),
            _brief(strategy="patch_localized_bug"),
        ]
        result = select_strategy(brief, previous_briefs=prev)
        assert result["action"] == "escalate"
        assert result["strategy"] == "reduce_scope_and_retry"

    def test_no_escalate_if_strategy_changed(self):
        brief = _brief(strategy="patch_localized_bug")
        prev = [
            _brief(strategy="add_missing_validation"),
            _brief(strategy="patch_localized_bug"),
        ]
        result = select_strategy(brief, previous_briefs=prev)
        assert result["action"] == "retry"

    def test_modifications_for_test_mismatch(self):
        result = select_strategy(_brief(strategy="repair_test_and_code_mismatch"))
        assert result["action"] == "retry"
        assert len(result["modifications"]) >= 1

    def test_re_run_gates_from_brief(self):
        result = select_strategy(_brief(failed_gates=["test_runner", "lint_checker"]))
        assert result["re_run_gates"] == ["test_runner", "lint_checker"]

    def test_no_previous_briefs(self):
        result = select_strategy(_brief())
        assert result["action"] == "retry"
