"""Review output parsing."""

import json

from cold_eyes.constants import SCHEMA_VERSION
from cold_eyes.schema import validate_review


def parse_review_output(raw_json_str):
    """Parse claude --output-format json output. Return dict."""
    try:
        raw = json.loads(raw_json_str)
        result_str = raw.get("result", "{}")
        if isinstance(result_str, str):
            cleaned = result_str.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines).strip()
            result = json.loads(cleaned)
        else:
            result = result_str
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
