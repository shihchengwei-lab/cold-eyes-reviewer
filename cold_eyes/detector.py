"""Detectors — state/invariant analysis and repo-specific focus selection."""

import re


# ---------------------------------------------------------------------------
# State / Invariant detector — regex signals in diff content
# ---------------------------------------------------------------------------

_STATE_PATTERNS = {
    # Order matters: more specific patterns first (first match wins per line).
    "state_check": re.compile(
        r"^[+-]\s*(if|elif|else if|case|switch|when|unless)"
        r"\b.*\b(state|status)\b", re.IGNORECASE),
    "transition_call": re.compile(
        r"^[+-]\s*.*(transition|set_state|set_status|setState|"
        r"update_status|change_state|move_to)\b", re.IGNORECASE),
    "fsm_pattern": re.compile(
        r"^[+-]\s*.*(fsm|finite.state|state.machine|workflow_step)", re.IGNORECASE),
    "rollback_pattern": re.compile(
        r"^[+-]\s*.*(rollback|revert_state|compensat|undo_transition)", re.IGNORECASE),
    "state_assignment": re.compile(
        r"^[+-]\s*.*\b(state|status)\s*[=:]\s*", re.IGNORECASE),
}


def detect_state_signals(diff_text):
    """Scan diff for state/invariant patterns.

    Returns list of dicts: {signal_type, line}.
    Only added/removed lines are checked (not headers).
    """
    signals = []
    for line in diff_text.split("\n"):
        stripped = line.rstrip()
        if not stripped or stripped.startswith(("+++", "---", "@@")):
            continue
        for name, pattern in _STATE_PATTERNS.items():
            if pattern.search(stripped):
                signals.append({
                    "signal_type": name,
                    "line": stripped[:120],
                })
                break  # one signal per line
    return signals


# ---------------------------------------------------------------------------
# Repo-type classifier — from file paths
# ---------------------------------------------------------------------------

_REPO_INDICATORS = {
    "web_backend": re.compile(
        r"(route|controller|handler|middleware|view[/\\s]|endpoint|server)",
        re.IGNORECASE),
    "sdk_library": re.compile(
        r"(sdk[/\\]|client[/\\]|lib[/\\]|setup\.py$|pyproject\.toml$)",
        re.IGNORECASE),
    "db_data": re.compile(
        r"(models?[/\\]|migrations?[/\\]|schema[/\\]|queries[/\\]|repository)",
        re.IGNORECASE),
    "infra_async": re.compile(
        r"(worker[/\\]|queue[/\\]|celery|tasks?[/\\]|docker|k8s|deploy)",
        re.IGNORECASE),
}


def classify_repo_type(files):
    """Classify repo type from changed file paths.

    Returns (repo_type, scores).
    repo_type: web_backend | sdk_library | db_data | infra_async | general.
    """
    scores = {k: 0 for k in _REPO_INDICATORS}
    for f in files:
        normalized = f.replace("\\", "/")
        for rtype, pattern in _REPO_INDICATORS.items():
            if pattern.search(normalized):
                scores[rtype] += 1

    if not any(scores.values()):
        return "general", scores

    best = max(scores, key=scores.get)
    return best, scores


# ---------------------------------------------------------------------------
# Detector focus profiles — per repo type
# ---------------------------------------------------------------------------

_DETECTOR_FOCUS = {
    "web_backend": {
        "name": "auth / permission",
        "checks": [
            "Authentication bypass — is the auth check present on new/modified routes?",
            "Authorization gap — does the handler verify ownership/role before action?",
            "Missing middleware — is the security middleware applied to new endpoints?",
        ],
    },
    "sdk_library": {
        "name": "contract break",
        "checks": [
            "Breaking API change — has a public function signature changed?",
            "Missing deprecation — is the old API removed without notice?",
            "Type contract — do return types match documented shapes?",
        ],
    },
    "db_data": {
        "name": "migration / persistence",
        "checks": [
            "Schema drift — does code assume columns that don't exist yet or were dropped?",
            "Missing reverse migration — is there a rollback path?",
            "Serialization mismatch — does read code expect new shape while old data exists?",
        ],
    },
    "infra_async": {
        "name": "concurrency / staleness",
        "checks": [
            "Race condition — is shared state accessed without synchronization?",
            "Stale data — is a cached value used after it may have been invalidated?",
            "Missing error handling — does the async path handle timeout/retry?",
        ],
    },
    "general": {
        "name": "general",
        "checks": [],
    },
}


def get_detector_focus(repo_type):
    """Return the focus profile for a repo type."""
    return _DETECTOR_FOCUS.get(repo_type, _DETECTOR_FOCUS["general"])


# ---------------------------------------------------------------------------
# Build detector hints — combines state signals + repo-specific focus
# ---------------------------------------------------------------------------

def build_detector_hints(diff_text, files):
    """Build detector hint text from diff analysis and file classification.

    Returns dict:
        hint_text:       string to insert before diff (empty if no signals)
        state_signals:   list of detected state signals
        repo_type:       classified repo type
        detector_focus:  focus profile name
    """
    state_signals = detect_state_signals(diff_text)
    repo_type, _ = classify_repo_type(files)
    focus = get_detector_focus(repo_type)

    parts = []

    # State/invariant hints
    if state_signals:
        parts.append("[Cold Eyes: State/Invariant Detector]")
        parts.append(
            "State-related patterns detected. Pay extra attention to:")
        parts.append("- State updates missing pre-condition checks")
        parts.append("- Incomplete transitions (some fields updated, related fields missed)")
        parts.append("- Missing rollback or compensation logic")
        parts.append("- Broken validation order")
        sample = state_signals[:5]
        parts.append("Detected signals:")
        for s in sample:
            parts.append(f"  {s['signal_type']}: {s['line']}")
        if len(state_signals) > 5:
            parts.append(f"  ... and {len(state_signals) - 5} more")
        parts.append("[End State/Invariant Detector]")

    # Repo-specific hints
    if focus["checks"]:
        parts.append(f"[Cold Eyes: Repo-Specific Detector — {focus['name']}]")
        parts.append("Based on the changed files, also check:")
        for check in focus["checks"]:
            parts.append(f"- {check}")
        parts.append("[End Repo-Specific Detector]")

    hint_text = "\n".join(parts) + "\n" if parts else ""

    return {
        "hint_text": hint_text,
        "state_signals": state_signals,
        "repo_type": repo_type,
        "detector_focus": focus["name"],
    }
