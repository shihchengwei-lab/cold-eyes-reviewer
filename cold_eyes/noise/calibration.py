"""Confidence calibration integration — wrap v1 calibration for v2 findings."""

try:
    from cold_eyes.memory import extract_fp_patterns
    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False

try:
    from cold_eyes.policy import calibrate_evidence
    _HAS_POLICY = True
except ImportError:
    _HAS_POLICY = False


def calibrate(
    findings: list[dict],
    history_path: str | None = None,
) -> list[dict]:
    """Apply confidence calibration to v2 findings.

    Rules:
    1. Use v1 calibrate_evidence if available (handles evidence, abstain, FP)
    2. No-evidence downgrade: high confidence without supporting signals -> medium.
    """
    result: list[dict] = []

    # Try v1 calibration path
    v1_applied = False
    if _HAS_POLICY and _HAS_MEMORY:
        try:
            fp_patterns = extract_fp_patterns(history_path=history_path)
            v1_issues = [_to_v1_issue(f) for f in findings]
            calibrated = calibrate_evidence(v1_issues, fp_patterns)
            for i, f in enumerate(findings):
                try:
                    result.append(_merge_calibration(f, calibrated[i]))
                except Exception:
                    result.append(dict(f))
            v1_applied = True
        except Exception:
            result = [dict(f) for f in findings]
    else:
        result = [dict(f) for f in findings]

    # Additional v2-specific calibration
    for i, f in enumerate(result):
        try:
            # Skip v2 downgrade if v1 already changed this finding's confidence
            if v1_applied and f.get("confidence") != findings[i].get("confidence"):
                continue
            # No supporting signals + high confidence -> downgrade
            supporting = f.get("supporting", f.get("supporting_signals", []))
            message = f.get("message", "")
            if f.get("confidence") == "high" and not supporting and not message:
                f["confidence"] = "medium"
                f.setdefault("calibration_notes", []).append("no evidence → medium")
        except Exception:
            pass

    return result


def _to_v1_issue(finding: dict) -> dict:
    return {
        "check": finding.get("check", finding.get("code", "")),
        "verdict": finding.get("message", ""),
        "fix": "",
        "file": finding.get("file", finding.get("location", "")),
        "line_hint": finding.get("line", ""),
        "category": finding.get("category", "correctness"),
        "severity": finding.get("severity", "major"),
        "confidence": finding.get("confidence", "medium"),
        "evidence": finding.get("evidence", []),
        "what_would_falsify_this": "",
        "suggested_validation": "",
        "abstain_condition": finding.get("abstain_condition", ""),
    }


def _merge_calibration(original: dict, calibrated: dict) -> dict:
    """Merge v1 calibration result back into v2 finding."""
    result = dict(original)
    result["confidence"] = calibrated.get("confidence", original.get("confidence", "medium"))
    if "fp_match_count" in calibrated:
        result["fp_match_count"] = calibrated["fp_match_count"]
    return result
