"""Tests for the FP memory module."""

import json
import os
import sys
import tempfile

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cold_eyes.memory import extract_fp_patterns, match_fp_pattern


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_history(entries, path):
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _override_entry(issues, override_reason="false positive", ts="2026-04-10T12:00:00Z"):
    return {
        "version": 2,
        "timestamp": ts,
        "state": "overridden",
        "override_reason": override_reason,
        "review": {
            "schema_version": 1,
            "review_status": "completed",
            "pass": False,
            "issues": issues,
            "summary": "test",
        },
    }


def _blocked_entry(issues):
    return {
        "version": 2,
        "timestamp": "2026-04-10T12:00:00Z",
        "state": "blocked",
        "review": {
            "schema_version": 1,
            "review_status": "completed",
            "pass": False,
            "issues": issues,
            "summary": "test",
        },
    }


def _issue(category="state_invariant", file="src/models/order.py",
           check="Missing pre-condition check before state transition",
           severity="major", confidence="high"):
    return {
        "category": category,
        "file": file,
        "check": check,
        "verdict": "test verdict",
        "fix": "test fix",
        "severity": severity,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# extract_fp_patterns
# ---------------------------------------------------------------------------

class TestExtractFpPatterns:
    def test_empty_history(self, tmp_path):
        path = str(tmp_path / "empty.jsonl")
        _write_history([], path)
        result = extract_fp_patterns(history_path=path)
        assert result["total_overrides"] == 0
        assert result["total_issues"] == 0
        assert result["category_patterns"] == {}

    def test_no_file(self, tmp_path):
        path = str(tmp_path / "nonexistent.jsonl")
        result = extract_fp_patterns(history_path=path)
        assert result["total_overrides"] == 0

    def test_only_blocked_entries_ignored(self, tmp_path):
        path = str(tmp_path / "hist.jsonl")
        _write_history([_blocked_entry([_issue()])], path)
        result = extract_fp_patterns(history_path=path)
        assert result["total_overrides"] == 0
        assert result["total_issues"] == 0

    def test_category_pattern_extraction(self, tmp_path):
        path = str(tmp_path / "hist.jsonl")
        entries = [
            _override_entry([_issue(category="state_invariant")]),
            _override_entry([_issue(category="state_invariant")]),
            _override_entry([_issue(category="auth_permission")]),
        ]
        _write_history(entries, path)
        result = extract_fp_patterns(history_path=path, min_count=2)
        assert "state_invariant" in result["category_patterns"]
        assert result["category_patterns"]["state_invariant"] == 2
        assert "auth_permission" not in result["category_patterns"]

    def test_path_pattern_extraction(self, tmp_path):
        path = str(tmp_path / "hist.jsonl")
        entries = [
            _override_entry([_issue(file="src/models/order.py")]),
            _override_entry([_issue(file="src/models/user.py")]),
            _override_entry([_issue(file="src/views/dashboard.py")]),
        ]
        _write_history(entries, path)
        result = extract_fp_patterns(history_path=path, min_count=2)
        assert "src/models" in result["path_patterns"]
        assert result["path_patterns"]["src/models"] == 2

    def test_check_pattern_extraction(self, tmp_path):
        path = str(tmp_path / "hist.jsonl")
        same_check = "Missing pre-condition check before state transition"
        entries = [
            _override_entry([_issue(check=same_check)]),
            _override_entry([_issue(check=same_check)]),
            _override_entry([_issue(check="Unrelated check about something else entirely different")]),
        ]
        _write_history(entries, path)
        result = extract_fp_patterns(history_path=path, min_count=2)
        normalised = " ".join(same_check.lower().split()[:8])
        assert normalised in result["check_patterns"]

    def test_min_count_filters(self, tmp_path):
        path = str(tmp_path / "hist.jsonl")
        entries = [_override_entry([_issue(category="rare_cat")])]
        _write_history(entries, path)
        result = extract_fp_patterns(history_path=path, min_count=2)
        assert "rare_cat" not in result["category_patterns"]

    def test_min_count_1_includes_single(self, tmp_path):
        path = str(tmp_path / "hist.jsonl")
        entries = [_override_entry([_issue(category="once_cat")])]
        _write_history(entries, path)
        result = extract_fp_patterns(history_path=path, min_count=1)
        assert "once_cat" in result["category_patterns"]

    def test_last_days_filter(self, tmp_path):
        path = str(tmp_path / "hist.jsonl")
        entries = [
            _override_entry([_issue(category="old")], ts="2020-01-01T00:00:00Z"),
            _override_entry([_issue(category="old")], ts="2020-01-02T00:00:00Z"),
            _override_entry([_issue(category="recent")], ts="2026-04-11T00:00:00Z"),
            _override_entry([_issue(category="recent")], ts="2026-04-12T00:00:00Z"),
        ]
        _write_history(entries, path)
        result = extract_fp_patterns(history_path=path, min_count=2, last_days=30)
        assert "recent" in result["category_patterns"]
        assert "old" not in result["category_patterns"]

    def test_last_days_none_includes_all(self, tmp_path):
        path = str(tmp_path / "hist.jsonl")
        entries = [
            _override_entry([_issue(category="old")], ts="2020-01-01T00:00:00Z"),
            _override_entry([_issue(category="old")], ts="2020-01-02T00:00:00Z"),
        ]
        _write_history(entries, path)
        result = extract_fp_patterns(history_path=path, min_count=2, last_days=None)
        assert "old" in result["category_patterns"]

    def test_multiple_issues_per_entry(self, tmp_path):
        path = str(tmp_path / "hist.jsonl")
        entries = [
            _override_entry([_issue(category="a"), _issue(category="b")]),
            _override_entry([_issue(category="a"), _issue(category="b")]),
        ]
        _write_history(entries, path)
        result = extract_fp_patterns(history_path=path, min_count=2)
        assert result["total_issues"] == 4
        assert result["category_patterns"]["a"] == 2
        assert result["category_patterns"]["b"] == 2

    def test_malformed_json_lines_skipped(self, tmp_path):
        path = str(tmp_path / "hist.jsonl")
        with open(path, "w") as f:
            f.write("not json\n")
            f.write(json.dumps(_override_entry([_issue(category="ok")])) + "\n")
            f.write("{bad json\n")
            f.write(json.dumps(_override_entry([_issue(category="ok")])) + "\n")
        result = extract_fp_patterns(history_path=path, min_count=2)
        assert result["total_overrides"] == 2
        assert result["category_patterns"]["ok"] == 2

    def test_entry_without_review_skipped(self, tmp_path):
        path = str(tmp_path / "hist.jsonl")
        entry = {"version": 2, "state": "overridden", "timestamp": "2026-04-10T00:00:00Z"}
        _write_history([entry, entry], path)
        result = extract_fp_patterns(history_path=path)
        assert result["total_overrides"] == 2
        assert result["total_issues"] == 0

    def test_windows_backslash_path(self, tmp_path):
        path = str(tmp_path / "hist.jsonl")
        entries = [
            _override_entry([_issue(file="src\\models\\order.py")]),
            _override_entry([_issue(file="src\\models\\user.py")]),
        ]
        _write_history(entries, path)
        result = extract_fp_patterns(history_path=path, min_count=2)
        assert "src\\models" in result["path_patterns"]


# ---------------------------------------------------------------------------
# match_fp_pattern
# ---------------------------------------------------------------------------

class TestMatchFpPattern:
    @pytest.fixture
    def fp_patterns(self):
        return {
            "category_patterns": {"state_invariant": 5, "auth_permission": 3},
            "path_patterns": {"src/models": 4},
            "check_patterns": {"missing pre-condition check before state": 3},
            "total_overrides": 10,
            "total_issues": 15,
        }

    def test_no_match(self, fp_patterns):
        issue = _issue(category="unknown", file="lib/utils.py", check="Something new")
        count, types = match_fp_pattern(issue, fp_patterns)
        assert count == 0
        assert types == []

    def test_category_match(self, fp_patterns):
        issue = _issue(category="state_invariant", file="lib/utils.py", check="New check")
        count, types = match_fp_pattern(issue, fp_patterns)
        assert count == 1
        assert "category" in types

    def test_path_match(self, fp_patterns):
        issue = _issue(category="unknown", file="src/models/payment.py", check="New check")
        count, types = match_fp_pattern(issue, fp_patterns)
        assert count == 1
        assert "path" in types

    def test_check_match(self, fp_patterns):
        issue = _issue(
            category="unknown", file="lib/x.py",
            check="Missing pre-condition check before state transition in handler",
        )
        count, types = match_fp_pattern(issue, fp_patterns)
        assert count == 1
        assert "check" in types

    def test_double_match(self, fp_patterns):
        issue = _issue(
            category="state_invariant",
            file="src/models/order.py",
            check="New check entirely",
        )
        count, types = match_fp_pattern(issue, fp_patterns)
        assert count == 2
        assert "category" in types
        assert "path" in types

    def test_triple_match(self, fp_patterns):
        issue = _issue(
            category="state_invariant",
            file="src/models/order.py",
            check="Missing pre-condition check before state transition in handler",
        )
        count, types = match_fp_pattern(issue, fp_patterns)
        assert count == 3
        assert set(types) == {"category", "path", "check"}

    def test_empty_fp_patterns(self):
        issue = _issue()
        count, types = match_fp_pattern(issue, {})
        assert count == 0

    def test_none_fp_patterns(self):
        count, types = match_fp_pattern(_issue(), None)
        assert count == 0

    def test_none_issue(self):
        count, types = match_fp_pattern(None, {"category_patterns": {"a": 1}})
        assert count == 0

    def test_empty_issue(self):
        count, types = match_fp_pattern({}, {"category_patterns": {"a": 1}})
        assert count == 0

    def test_path_match_with_backslash(self, fp_patterns):
        issue = _issue(file="src\\models\\order.py")
        count, types = match_fp_pattern(issue, fp_patterns)
        assert "path" in types

    def test_path_exact_dir_match(self, fp_patterns):
        issue = _issue(file="src/models")
        count, types = match_fp_pattern(issue, fp_patterns)
        assert "path" in types

    def test_path_no_partial_prefix(self, fp_patterns):
        """src/models_v2/x.py should NOT match src/models."""
        issue = _issue(file="src/models_v2/order.py")
        count, types = match_fp_pattern(issue, fp_patterns)
        assert "path" not in types
