"""Tests for cold_eyes.gates.selection."""

from cold_eyes.gates.selection import build_gate_plan, select_gates


_ALL_GATES = ["llm_review", "test_runner", "lint_checker", "type_checker", "build_checker"]


class TestSelectGates:
    def test_no_gates_available(self):
        result = select_gates("high", [], [])
        assert result == []

    def test_contract_driven_test_pass(self):
        contracts = [{"check_type": "test_pass", "priority": "must"}]
        result = select_gates("low", contracts, _ALL_GATES)
        ids = {g["gate_id"] for g in result}
        assert "test_runner" in ids

    def test_contract_driven_lint(self):
        contracts = [{"check_type": "lint_clean", "priority": "should"}]
        result = select_gates("low", contracts, _ALL_GATES)
        ids = {g["gate_id"] for g in result}
        assert "lint_checker" in ids
        lint_entry = [g for g in result if g["gate_id"] == "lint_checker"][0]
        assert lint_entry["blocking"] == "soft"

    def test_must_priority_is_hard_blocking(self):
        contracts = [{"check_type": "test_pass", "priority": "must"}]
        result = select_gates("low", contracts, _ALL_GATES)
        entry = [g for g in result if g["gate_id"] == "test_runner"][0]
        assert entry["blocking"] == "hard"

    def test_high_risk_selects_all(self):
        result = select_gates("high", [], _ALL_GATES)
        ids = {g["gate_id"] for g in result}
        assert ids == set(_ALL_GATES)

    def test_critical_risk_selects_all(self):
        result = select_gates("critical", [], _ALL_GATES)
        assert len(result) == len(_ALL_GATES)

    def test_low_risk_no_contracts_fallback(self):
        result = select_gates("low", [], _ALL_GATES)
        assert len(result) == 1
        assert result[0]["gate_id"] == "llm_review"
        assert result[0]["blocking"] == "soft"

    def test_no_duplicate_gates(self):
        contracts = [
            {"check_type": "test_pass", "priority": "must"},
            {"check_type": "test_pass", "priority": "should"},
        ]
        result = select_gates("low", contracts, _ALL_GATES)
        ids = [g["gate_id"] for g in result]
        assert len(ids) == len(set(ids))

    def test_unavailable_gate_not_selected(self):
        contracts = [{"check_type": "test_pass", "priority": "must"}]
        result = select_gates("low", contracts, ["llm_review"])
        ids = {g["gate_id"] for g in result}
        assert "test_runner" not in ids


class TestBuildGatePlan:
    def test_includes_skipped(self):
        contracts = [{"check_type": "test_pass", "priority": "must"}]
        plan = build_gate_plan("low", contracts, _ALL_GATES)
        assert "selected_gates" in plan
        assert "skipped_gates" in plan
        selected_ids = {g["gate_id"] for g in plan["selected_gates"]}
        skipped_ids = {g["gate_id"] for g in plan["skipped_gates"]}
        assert selected_ids & skipped_ids == set()  # no overlap
        assert selected_ids | skipped_ids == set(_ALL_GATES)

    def test_risk_level_in_plan(self):
        plan = build_gate_plan("medium", [], _ALL_GATES)
        assert plan["risk_level"] == "medium"
