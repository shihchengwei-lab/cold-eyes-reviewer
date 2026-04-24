"""Review output parsing."""

import json
import os
import time

from cold_eyes.constants import SCHEMA_VERSION
from cold_eyes.schema import validate_review


def _dump_parse_failure(raw_json_str, error):
    """Best-effort dump of unparseable engine stdout for later forensics.

    Writes to ~/.claude/cold-review-debug/<ts>-<pid>.txt. Silent on any failure —
    parse recovery must never itself raise.
    """
    try:
        debug_dir = os.path.join(
            os.path.expanduser("~"), ".claude", "cold-review-debug"
        )
        os.makedirs(debug_dir, exist_ok=True)
        fname = f"{int(time.time())}-{os.getpid()}.txt"
        with open(os.path.join(debug_dir, fname), "w", encoding="utf-8") as f:
            f.write(f"# parse error: {error}\n")
            f.write(f"# raw length: {len(raw_json_str)}\n")
            f.write("# --- raw stdout below ---\n")
            f.write(raw_json_str)
    except Exception:
        pass


def _extract_result_object(raw_json_str):
    """Extract the result JSON object from claude CLI stdout.

    claude --output-format json can emit either a single JSON object or
    multiple back-to-back JSON objects (e.g. a {"type":"system","subtype":"init",...}
    preamble followed by the actual {"type":"result",...} payload).  Use raw_decode
    to iterate all top-level JSON objects and pick the one carrying the result.
    """
    decoder = json.JSONDecoder()
    text = raw_json_str.lstrip()
    objects = []
    while text:
        try:
            obj, idx = decoder.raw_decode(text)
        except json.JSONDecodeError:
            break
        objects.append(obj)
        text = text[idx:].lstrip()

    if not objects:
        return json.loads(raw_json_str)

    for obj in objects:
        if isinstance(obj, dict) and (obj.get("type") == "result" or "result" in obj):
            return obj
    return objects[-1]


def parse_review_output(raw_json_str):
    """Parse claude --output-format json output. Return dict."""
    try:
        raw = _extract_result_object(raw_json_str)
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
        _dump_parse_failure(raw_json_str, e)
        return {
            "schema_version": SCHEMA_VERSION,
            "pass": True,
            "review_status": "failed",
            "issues": [],
            "summary": f"Parse error: {e}",
        }
