"""Review output parsing."""

import json

from cold_eyes.constants import SCHEMA_VERSION
from cold_eyes.schema import validate_review


def parse_review_output(raw_json_str):
    """Parse claude --output-format json output. Return dict."""
    try:
        raw = json.loads(raw_json_str)
        # Handle both wrapped ({"result": "..."}) and unwrapped formats
        if "result" in raw:
            result_str = raw["result"]
            # Bug #69: Claude returns {"result": null} — treat as failed review
            if result_str is None:
                return {
                    "schema_version": SCHEMA_VERSION,
                    "pass": False,
                    "review_status": "failed",
                    "issues": [],
                    "summary": "LLM returned null result",
                }
            if isinstance(result_str, str):
                cleaned = result_str.strip()
                if cleaned.startswith("```"):
                    lines = cleaned.split("\n")
                    if lines and lines[0].strip().startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip().startswith("```"):
                        lines = lines[:-1]
                    cleaned = "\n".join(lines).strip()
                result = json.loads(cleaned)
            else:
                result = result_str
        else:
            # Unwrapped: raw itself is the review dict
            result = raw
        result.setdefault("schema_version", SCHEMA_VERSION)
        result.setdefault("review_status", "completed")
        result.setdefault("pass", True)
        result.setdefault("issues", [])
        result.setdefault("summary", "")
        for issue in result["issues"]:
            issue.setdefault("severity", "major")
            issue.setdefault("confidence", "medium")
            issue.setdefault("category", "correctness")
            issue.setdefault("file", "unknown")
            issue.setdefault("line_hint", "")
            issue.setdefault("evidence", [])
            issue.setdefault("what_would_falsify_this", "")
            issue.setdefault("suggested_validation", "")
            issue.setdefault("abstain_condition", "")
        ok, errors = validate_review(result)
        if not ok:
            result["validation_errors"] = errors
        return result
    except Exception as e:
        return {
            "schema_version": SCHEMA_VERSION,
            "pass": True,
            "review_status": "failed",
            "issues": [],
            "summary": f"Parse error: {e}",
        }
