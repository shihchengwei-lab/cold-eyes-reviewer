"""Gate result normalizer — convert raw gate outputs to GateResult."""

from cold_eyes.type_defs import GateResult, generate_id


def normalize_result(
    gate_name: str,
    raw_output: str,
    exit_code: int,
    duration_ms: int = 0,
    blocking_mode: str = "soft",
) -> GateResult:
    """Convert raw gate output into a normalized GateResult.

    Uses gate-specific parsers when available, falls back to generic.
    """
    parser = _PARSERS.get(gate_name, _parse_generic)
    status, findings, warnings = parser(raw_output, exit_code)

    return GateResult(
        gate_id=generate_id(),
        gate_name=gate_name,
        status=status,
        blocking_mode=blocking_mode,
        findings=findings,
        warnings=warnings,
        raw_output=raw_output[:5000],  # cap raw output
        duration_ms=duration_ms,
        metadata={},
    )


# ---------------------------------------------------------------------------
# Gate-specific parsers
# ---------------------------------------------------------------------------

def _parse_generic(raw: str, exit_code: int) -> tuple[str, list[dict], list[str]]:
    status = "pass" if exit_code == 0 else "fail"
    findings: list[dict] = []
    if exit_code != 0 and raw.strip():
        findings.append({"type": "raw_error", "message": raw.strip()[:2000]})
    return status, findings, []


def _parse_pytest(raw: str, exit_code: int) -> tuple[str, list[dict], list[str]]:
    status = "pass" if exit_code == 0 else "fail"
    findings: list[dict] = []
    warnings: list[str] = []

    for line in raw.splitlines():
        line_s = line.strip()
        # FAILED tests/test_foo.py::TestBar::test_baz - AssertionError: ...
        if line_s.startswith("FAILED "):
            parts = line_s[7:].split(" - ", 1)
            loc = parts[0]
            msg = parts[1] if len(parts) > 1 else ""
            findings.append({"type": "test_failure", "location": loc, "message": msg})
        # ERROR tests/test_foo.py::...
        elif line_s.startswith("ERROR "):
            findings.append({"type": "test_error", "location": line_s[6:], "message": ""})
        # warnings summary
        elif "warning" in line_s.lower() and "::" not in line_s:
            warnings.append(line_s)

    if exit_code != 0 and not findings:
        findings.append({"type": "raw_error", "message": raw.strip()[:2000]})

    return status, findings, warnings


def _parse_ruff(raw: str, exit_code: int) -> tuple[str, list[dict], list[str]]:
    status = "pass" if exit_code == 0 else "fail"
    findings: list[dict] = []

    for line in raw.splitlines():
        line_s = line.strip()
        if ":" not in line_s or not any(c in line_s for c in ("E", "F", "W")):
            continue
        # Split with enough parts to handle Windows drive letter (C:\path:line:col: msg)
        parts = line_s.split(":", 4)
        if len(parts[0]) == 1 and parts[0].isalpha() and len(parts) >= 5:
            file_path = parts[0] + ":" + parts[1]
            line_no = parts[2]
            message = parts[4].strip()
        elif len(parts) >= 4:
            file_path = parts[0]
            line_no = parts[1]
            message = parts[3].strip()
        else:
            continue
        findings.append({
            "type": "lint_violation",
            "file": file_path,
            "line": line_no,
            "code": message.split(" ")[0] if message else "",
            "message": message,
        })

    return status, findings, []


def _parse_llm_review(raw: str, exit_code: int) -> tuple[str, list[dict], list[str]]:
    """Parse v1 engine.run() FinalOutcome wrapped as raw output."""
    import json
    status = "pass" if exit_code == 0 else "fail"
    findings: list[dict] = []
    warnings: list[str] = []

    try:
        outcome = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        if exit_code != 0:
            findings.append({"type": "raw_error", "message": raw.strip()[:2000]})
        return status, findings, warnings

    state = outcome.get("state", "")
    if state in ("blocked", "infra_failed"):
        status = "fail"
    elif state in ("passed", "skipped", "reported"):
        status = "pass"

    for issue in outcome.get("issues", []):
        findings.append({
            "type": "review_finding",
            "check": issue.get("check", "") or "",
            "severity": issue.get("severity", "") or "",
            "confidence": issue.get("confidence", "") or "",
            "file": issue.get("file", "") or "",
            "message": issue.get("verdict", "") or "",
        })

    return status, findings, warnings


_PARSERS = {
    "test_runner": _parse_pytest,
    "lint_checker": _parse_ruff,
    "llm_review": _parse_llm_review,
}
