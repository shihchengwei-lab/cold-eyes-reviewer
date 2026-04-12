"""Failure signal parser — extract actionable signals from gate output."""

import re


def extract_signals(gate_result: dict) -> list[str]:
    """Extract actionable signals from a gate result.

    Returns a list of human-readable signal strings that can be used
    to guide a retry attempt.
    """
    gate_name = gate_result.get("gate_name", "")
    parser = _PARSERS.get(gate_name, _extract_generic)
    return parser(gate_result)


# ---------------------------------------------------------------------------
# Gate-specific extractors
# ---------------------------------------------------------------------------

def _extract_generic(gate_result: dict) -> list[str]:
    signals: list[str] = []
    for f in gate_result.get("findings", []):
        msg = f.get("message", "")
        if msg:
            signals.append(msg[:200])
    if not signals:
        raw = gate_result.get("raw_output", "")
        if raw:
            signals.append(f"raw output: {raw[:200]}")
    return signals


def _extract_pytest(gate_result: dict) -> list[str]:
    signals: list[str] = []
    for f in gate_result.get("findings", []):
        loc = f.get("location", "")
        msg = f.get("message", "")
        if f.get("type") == "test_failure":
            signals.append(f"test failed: {loc}" + (f" — {msg}" if msg else ""))
        elif f.get("type") == "test_error":
            signals.append(f"test error: {loc}")

    # Try to extract file:line from raw output tracebacks
    raw = gate_result.get("raw_output", "")
    for match in re.finditer(r'File "([^"]+)", line (\d+)', raw):
        filepath, line = match.group(1), match.group(2)
        if "site-packages" not in filepath:
            signal = f"traceback: {filepath}:{line}"
            if signal not in signals:
                signals.append(signal)

    return signals


def _extract_ruff(gate_result: dict) -> list[str]:
    signals: list[str] = []
    for f in gate_result.get("findings", []):
        if f.get("type") == "lint_violation":
            file_ = f.get("file", "")
            line = f.get("line", "")
            code = f.get("code", "")
            msg = f.get("message", "")
            signals.append(f"lint: {file_}:{line} {code} {msg}".strip())
    return signals


def _extract_llm_review(gate_result: dict) -> list[str]:
    signals: list[str] = []
    for f in gate_result.get("findings", []):
        if f.get("type") == "review_finding":
            check = f.get("check", "")
            file_ = f.get("file", "")
            sev = f.get("severity", "")
            msg = f.get("message", "")
            signals.append(
                f"[{sev}] {check} in {file_}" + (f" — {msg}" if msg else "")
            )
    return signals


_PARSERS = {
    "test_runner": _extract_pytest,
    "lint_checker": _extract_ruff,
    "llm_review": _extract_llm_review,
}
