"""Failure taxonomy — classify gate failures into actionable types."""

from cold_eyes.type_defs import FailureType

# Map (gate_name, finding_type) -> failure category
_GATE_TYPE_MAP: dict[tuple[str, str], str] = {
    ("test_runner", "test_failure"):    "test_regression",
    ("test_runner", "test_error"):      "missing_import_or_dependency",
    ("lint_checker", "lint_violation"):  "insufficient_validation",
    ("type_checker", "type_error"):     "insufficient_validation",
    ("build_checker", "build_error"):   "build_or_install_failure",
    ("llm_review", "review_finding"):   "low_confidence_suspicion",
}

# Subcategory detection by keyword in message
_SUBCATEGORY_KEYWORDS: dict[str, list[tuple[str, str]]] = {
    "test_regression": [
        ("import", "import_error"),
        ("fixture", "fixture_missing"),
        ("assert", "assertion_error"),
        ("timeout", "test_timeout"),
    ],
    "missing_import_or_dependency": [
        ("ModuleNotFoundError", "missing_module"),
        ("ImportError", "import_error"),
    ],
    "build_or_install_failure": [
        ("syntax", "syntax_error"),
        ("compile", "compilation_error"),
    ],
}

# Transient failure types (may succeed on retry without code changes)
_TRANSIENT = {"build_or_install_failure"}

_TYPICAL_FIX: dict[str, str] = {
    "test_regression": "fix failing assertion or update test expectations",
    "missing_import_or_dependency": "add missing import or install dependency",
    "build_or_install_failure": "fix build/install configuration",
    "syntax_or_parse_failure": "fix syntax error at indicated location",
    "contract_break": "restore invariant broken by the change",
    "state_invariant_suspicion": "verify state transitions are preserved",
    "schema_or_migration_risk": "check migration reversibility and data safety",
    "async_or_concurrency_risk": "add synchronisation or fix race condition",
    "insufficient_validation": "add missing validation or fix lint/type errors",
    "low_confidence_suspicion": "review flagged issue and decide if real",
    "unknown": "inspect raw gate output for details",
}


def classify_failure(gate_result: dict) -> FailureType:
    """Classify a gate result into a FailureType.

    Uses gate name + finding types to determine category.
    Falls back to 'unknown' if no match.
    """
    gate_name = gate_result.get("gate_name", "")
    findings = gate_result.get("findings", [])

    if not findings:
        return FailureType(
            category="unknown",
            subcategory="no_findings",
            is_transient=False,
            typical_fix=_TYPICAL_FIX.get("unknown", ""),
        )

    # Use the first finding to determine category
    first = findings[0]
    finding_type = first.get("type", "")
    message = first.get("message", "") + " " + first.get("location", "")

    key = (gate_name, finding_type)
    category = _GATE_TYPE_MAP.get(key, "unknown")

    # Severity/confidence upgrade for LLM review findings
    if category == "low_confidence_suspicion" and gate_name == "llm_review":
        severity = first.get("severity", "")
        confidence = first.get("confidence", "")
        if severity == "critical" and confidence == "high":
            category = "contract_break"
        elif severity == "critical":
            category = "state_invariant_suspicion"

    subcategory = _detect_subcategory(category, message)
    is_transient = category in _TRANSIENT

    return FailureType(
        category=category,
        subcategory=subcategory,
        is_transient=is_transient,
        typical_fix=_TYPICAL_FIX.get(category, ""),
    )


def _detect_subcategory(category: str, message: str) -> str:
    keywords = _SUBCATEGORY_KEYWORDS.get(category, [])
    for keyword, sub in keywords:
        if keyword.lower() in message.lower():
            return sub
    return "general"
