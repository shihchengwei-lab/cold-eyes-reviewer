"""Shared v2 type definitions — single source of truth for all v2 modules.

Pure structure definitions (TypedDict) and tiny helpers (ID generation,
timestamps).  No business logic, no imports of other cold_eyes modules
except constants.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, TypedDict

# ---------------------------------------------------------------------------
# Re-export v1 orderings so v2 modules only need to import type_defs.py
# ---------------------------------------------------------------------------
from cold_eyes.constants import (  # noqa: F401
    CONFIDENCE_ORDER,
    SEVERITY_ORDER,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def generate_id() -> str:
    """Return a short, unique identifier (12 hex chars)."""
    return uuid.uuid4().hex[:12]


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Session types
# ---------------------------------------------------------------------------

SessionState = Literal[
    "created",
    "contract_generated",
    "gates_planned",
    "gates_running",
    "gates_failed",
    "retrying",
    "passed",
    "failed_terminal",
    "aborted",
]

SESSION_STATES: list[str] = [
    "created", "contract_generated", "gates_planned", "gates_running",
    "gates_failed", "retrying", "passed", "failed_terminal", "aborted",
]


class SessionEvent(TypedDict, total=False):
    """A single lifecycle event inside a session."""
    event_type: str          # required by convention
    timestamp: str           # ISO-8601
    from_state: str
    to_state: str
    data: dict               # arbitrary payload


class SessionRecord(TypedDict, total=False):
    """Top-level session object persisted to the store."""
    session_id: str          # required
    task_description: str    # required
    state: str               # SessionState
    created_at: str          # ISO-8601
    updated_at: str          # ISO-8601
    changed_files: list[str]
    change_summary: str
    events: list[dict]       # list of SessionEvent
    contracts: list[dict]    # list of CorrectnessContract
    gate_plan: list[str]     # ordered gate names
    gate_results: list[dict] # list of GateResult
    retry_briefs: list[dict] # list of RetryBrief
    final_outcome: dict      # v1-compatible FinalOutcome or None
    learning_signals: dict   # post-session observations


# ---------------------------------------------------------------------------
# Contract types
# ---------------------------------------------------------------------------

ContractPriority = Literal["must", "should", "nice"]


class CorrectnessContract(TypedDict, total=False):
    """A single correctness expectation for the change under review."""
    contract_id: str
    intended_change: str
    problem_being_solved: str
    non_goals: list[str]
    must_not_break: list[str]
    assumed_invariants: list[str]
    touched_interfaces: list[str]
    risk_categories: list[str]
    risky_surfaces: list[str]
    validation_plan: str
    minimum_tests_to_pass: list[str]
    new_tests_to_add: list[str]
    likely_failure_modes: list[str]
    first_debug_targets: list[str]
    rollback_guess: str
    check_type: str          # "test_pass", "lint_clean", "llm_review", etc.
    target_files: list[str]
    priority: str            # ContractPriority


# ---------------------------------------------------------------------------
# Gate types
# ---------------------------------------------------------------------------

GateStatus = Literal["pass", "fail", "error", "skip"]

GATE_STATUSES: list[str] = ["pass", "fail", "error", "skip"]


class GateResult(TypedDict, total=False):
    """Normalised output from a single gate execution."""
    gate_id: str
    gate_name: str
    status: str              # GateStatus
    blocking_mode: str       # "hard" | "soft"
    findings: list[dict]
    warnings: list[str]
    raw_output: str
    duration_ms: int
    metadata: dict


# ---------------------------------------------------------------------------
# Failure / Retry types
# ---------------------------------------------------------------------------

FailureCategory = Literal[
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
]

FAILURE_CATEGORIES: list[str] = [
    "syntax_or_parse_failure", "missing_import_or_dependency",
    "build_or_install_failure", "test_regression", "contract_break",
    "state_invariant_suspicion", "schema_or_migration_risk",
    "async_or_concurrency_risk", "insufficient_validation",
    "low_confidence_suspicion", "unknown",
]


class FailureType(TypedDict, total=False):
    """Classified failure from a gate result."""
    category: str            # FailureCategory
    subcategory: str
    is_transient: bool
    typical_fix: str


class RetryBrief(TypedDict, total=False):
    """Structured instruction set for the next retry iteration."""
    retry_id: str
    failure_summary: str
    failed_gates: list[str]
    probable_failure_types: list[str]
    most_likely_root_causes: list[str]
    minimal_fix_scope: list[str]
    files_to_reinspect: list[str]
    must_preserve_constraints: list[str]
    tests_to_run_after_fix: list[str]
    tests_to_add_or_adjust: list[str]
    do_not_repeat: list[str]
    retry_strategy: str
    confidence: str          # "high" | "medium" | "low"
    stop_if_repeated: bool
    retry_count: int


# ---------------------------------------------------------------------------
# Noise types
# ---------------------------------------------------------------------------

class FindingCluster(TypedDict, total=False):
    """A group of related findings sharing a probable root cause."""
    cluster_id: str
    probable_root_cause: str
    supporting_signals: list[str]
    affected_files: list[str]
    recommended_fix_scope: str
    confidence: str
