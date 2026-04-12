"""Tests for cold_eyes.types — shared v2 type definitions."""

import re
from cold_eyes.type_defs import (
    CONFIDENCE_ORDER,
    FAILURE_CATEGORIES,
    GATE_STATUSES,
    SESSION_STATES,
    SEVERITY_ORDER,
    CorrectnessContract,
    FailureType,
    FindingCluster,
    GateResult,
    RetryBrief,
    SessionEvent,
    SessionRecord,
    generate_id,
    now_iso,
)


class TestGenerateId:
    def test_returns_12_hex_chars(self):
        sid = generate_id()
        assert len(sid) == 12
        assert re.fullmatch(r"[0-9a-f]{12}", sid)

    def test_ids_are_unique(self):
        ids = {generate_id() for _ in range(100)}
        assert len(ids) == 100


class TestNowIso:
    def test_returns_iso_string(self):
        ts = now_iso()
        # Must contain date separator and timezone info
        assert "T" in ts
        assert "+" in ts or "Z" in ts or ts.endswith("+00:00")

    def test_successive_calls_are_monotonic(self):
        t1 = now_iso()
        t2 = now_iso()
        assert t2 >= t1


class TestSessionStates:
    def test_contains_all_required_states(self):
        required = {
            "created", "contract_generated", "gates_planned",
            "gates_running", "gates_failed", "retrying",
            "passed", "failed_terminal", "aborted",
        }
        assert required == set(SESSION_STATES)

    def test_is_list_of_strings(self):
        assert isinstance(SESSION_STATES, list)
        assert all(isinstance(s, str) for s in SESSION_STATES)


class TestGateStatuses:
    def test_contains_all_statuses(self):
        assert set(GATE_STATUSES) == {"pass", "fail", "error", "skip"}


class TestFailureCategories:
    def test_contains_all_categories(self):
        expected = {
            "syntax_or_parse_failure",
            "missing_import_or_dependency",
            "build_or_install_failure",
            "test_regression",
            "contract_break",
            "state_invariant_suspicion",
            "schema_or_migration_risk",
            "async_or_concurrency_risk",
            "insufficient_validation",
            "low_confidence_suspicion",
            "unknown",
        }
        assert expected == set(FAILURE_CATEGORIES)


class TestReExports:
    def test_severity_order(self):
        assert SEVERITY_ORDER["critical"] > SEVERITY_ORDER["major"]
        assert SEVERITY_ORDER["major"] > SEVERITY_ORDER["minor"]

    def test_confidence_order(self):
        assert CONFIDENCE_ORDER["high"] > CONFIDENCE_ORDER["medium"]
        assert CONFIDENCE_ORDER["medium"] > CONFIDENCE_ORDER["low"]


class TestTypedDictStructures:
    """Verify TypedDicts can be instantiated as plain dicts."""

    def test_session_record_minimal(self):
        s: SessionRecord = {
            "session_id": generate_id(),
            "task_description": "test",
            "state": "created",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        assert s["state"] == "created"

    def test_session_event(self):
        e: SessionEvent = {
            "event_type": "state_change",
            "timestamp": now_iso(),
            "from_state": "created",
            "to_state": "contract_generated",
        }
        assert e["event_type"] == "state_change"

    def test_correctness_contract_minimal(self):
        c: CorrectnessContract = {
            "contract_id": generate_id(),
            "intended_change": "add login endpoint",
            "check_type": "llm_review",
            "priority": "must",
        }
        assert c["priority"] == "must"

    def test_gate_result(self):
        g: GateResult = {
            "gate_id": generate_id(),
            "gate_name": "llm_review",
            "status": "pass",
            "findings": [],
            "duration_ms": 1200,
        }
        assert g["status"] == "pass"

    def test_failure_type(self):
        f: FailureType = {
            "category": "test_regression",
            "subcategory": "assertion_error",
            "is_transient": False,
            "typical_fix": "fix assertion or code",
        }
        assert f["category"] == "test_regression"

    def test_retry_brief(self):
        b: RetryBrief = {
            "retry_id": generate_id(),
            "failure_summary": "2 tests failed",
            "retry_strategy": "patch_localized_bug",
            "confidence": "medium",
            "retry_count": 1,
        }
        assert b["retry_count"] == 1

    def test_finding_cluster(self):
        fc: FindingCluster = {
            "cluster_id": generate_id(),
            "probable_root_cause": "missing import",
            "affected_files": ["src/main.py"],
            "confidence": "high",
        }
        assert fc["probable_root_cause"] == "missing import"
