"""Eval runner — deterministic, benchmark, and sweep modes.

Deterministic mode tests the decision boundary (parse + policy) using
mock responses embedded in case files.  No git, no model calls.

Benchmark mode sends real diffs to a model and records responses.

Sweep mode replays saved responses across threshold x confidence combinations
to compute precision / recall / F1.
"""

import datetime
import json
import os
import glob as _glob

# Allow running from project root
import sys
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from cold_eyes import __version__
from cold_eyes.review import parse_review_output
from cold_eyes.policy import apply_policy
from cold_eyes.constants import SEVERITY_ORDER

_EVAL_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Case loading
# ---------------------------------------------------------------------------

def load_cases(cases_dir):
    """Load all JSON eval cases from a directory.  Return sorted list."""
    pattern = os.path.join(cases_dir, "*.json")
    cases = []
    for path in sorted(_glob.glob(pattern)):
        with open(path, "r", encoding="utf-8") as f:
            case = json.load(f)
        # Validate required fields
        for field in ("id", "category", "description", "diff", "mock_response", "ground_truth"):
            if field not in case:
                raise ValueError(f"{os.path.basename(path)}: missing required field '{field}'")
        cases.append(case)
    return cases


def validate_manifest(cases_dir):
    """Validate manifest.json against actual case files.  Return (ok, errors)."""
    manifest_path = os.path.join(os.path.dirname(cases_dir), "manifest.json")
    if not os.path.isfile(manifest_path):
        return False, ["manifest.json not found"]
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    cases = load_cases(cases_dir)

    errors = []
    case_ids = {c["id"] for c in cases}
    case_by_id = {c["id"]: c for c in cases}
    manifest_ids = set()
    for cat, info in manifest.get("categories", {}).items():
        for cid in info.get("cases", []):
            manifest_ids.add(cid)
            if cid not in case_ids:
                errors.append(f"manifest lists '{cid}' but no case file found")
            elif case_by_id[cid]["category"] != cat:
                errors.append(f"'{cid}' category mismatch: manifest={cat}, file={case_by_id[cid]['category']}")
        actual_count = sum(1 for c in cases if c["category"] == cat)
        if info.get("count") != actual_count:
            errors.append(f"category '{cat}' count mismatch: manifest={info.get('count')}, actual={actual_count}")

    for cid in case_ids - manifest_ids:
        errors.append(f"case '{cid}' exists but not in manifest")

    if manifest.get("total_cases") != len(cases):
        errors.append(f"total_cases mismatch: manifest={manifest.get('total_cases')}, actual={len(cases)}")

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Report envelope
# ---------------------------------------------------------------------------

def _make_report(mode_result):
    """Wrap a mode result with metadata envelope."""
    return {
        "cold_eyes_version": __version__,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "eval_schema_version": _EVAL_SCHEMA_VERSION,
        **mode_result,
    }


# ---------------------------------------------------------------------------
# Deterministic mode
# ---------------------------------------------------------------------------

def _evaluate_case(case, threshold="critical", confidence="medium"):
    """Evaluate a single case against its embedded mock response.

    Pipeline: parse_review_output(mock_response) -> apply_policy() -> compare.
    """
    mock = case["mock_response"]
    raw_str = json.dumps(mock) if isinstance(mock, dict) else mock
    review = parse_review_output(raw_str)

    settings = case.get("settings", {})
    truncated = settings.get("truncated", False)
    skipped_files = settings.get("skipped_files", [])

    fp_patterns = case.get("fp_patterns")

    outcome = apply_policy(
        review, mode="block", threshold=threshold, allow_once=False,
        min_confidence=confidence, truncated=truncated,
        skipped_files=skipped_files, fp_patterns=fp_patterns,
    )

    gt = case["ground_truth"]
    actual_block = outcome["action"] == "block"
    expected_block = gt["should_block"]
    match = actual_block == expected_block

    # Check severity if specified
    severity_ok = True
    if "min_severity" in gt and not gt.get("should_block", False):
        pass  # Only check severity for expected blocks
    elif "min_severity" in gt and actual_block:
        issues = review.get("issues", [])
        if issues:
            max_sev = max(SEVERITY_ORDER.get(i.get("severity", "major"), 2) for i in issues)
            min_required = SEVERITY_ORDER.get(gt["min_severity"], 2)
            severity_ok = max_sev >= min_required

    return {
        "id": case["id"],
        "category": case["category"],
        "expected_block": expected_block,
        "actual_block": actual_block,
        "match": match and severity_ok,
        "severity_ok": severity_ok,
        "actual_action": outcome["action"],
        "actual_state": outcome.get("state", ""),
    }


def run_deterministic(cases_dir, threshold="critical", confidence="medium"):
    """Run all cases with embedded mock responses.  Return EvalReport dict."""
    cases = load_cases(cases_dir)
    results = []
    for case in cases:
        # Skip cases that expect engine-level skip (empty diff)
        if case.get("settings", {}).get("expect_skip"):
            results.append({
                "id": case["id"],
                "category": case["category"],
                "expected_block": False,
                "actual_block": False,
                "match": True,
                "severity_ok": True,
                "actual_action": "skip",
                "actual_state": "skipped",
            })
            continue
        results.append(_evaluate_case(case, threshold, confidence))

    passed = sum(1 for r in results if r["match"])
    return _make_report({
        "mode": "deterministic",
        "threshold": threshold,
        "confidence": confidence,
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "cases": results,
    })


# ---------------------------------------------------------------------------
# Threshold sweep
# ---------------------------------------------------------------------------

_THRESHOLDS = ["critical", "major"]
_CONFIDENCES = ["high", "medium", "low"]


def threshold_sweep(cases_dir):
    """Run all cases across threshold x confidence combinations.

    Return SweepReport with precision/recall/F1 per combination.
    """
    cases = load_cases(cases_dir)
    sweep = []

    for thr in _THRESHOLDS:
        for conf in _CONFIDENCES:
            tp = fp = fn = tn = 0
            for case in cases:
                if case.get("settings", {}).get("expect_skip"):
                    # Skip cases always pass
                    gt_block = case["ground_truth"]["should_block"]
                    if gt_block:
                        fn += 1
                    else:
                        tn += 1
                    continue

                result = _evaluate_case(case, thr, conf)
                gt_block = case["ground_truth"]["should_block"]

                if result["actual_block"] and gt_block:
                    tp += 1
                elif result["actual_block"] and not gt_block:
                    fp += 1
                elif not result["actual_block"] and gt_block:
                    fn += 1
                else:
                    tn += 1

            precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

            sweep.append({
                "threshold": thr,
                "confidence": conf,
                "true_positives": tp,
                "false_positives": fp,
                "false_negatives": fn,
                "true_negatives": tn,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
            })

    # Find best F1
    best = max(sweep, key=lambda s: s["f1"])
    return _make_report({
        "mode": "sweep",
        "combinations": len(sweep),
        "sweep": sweep,
        "recommended": {
            "threshold": best["threshold"],
            "confidence": best["confidence"],
            "f1": best["f1"],
        },
    })


# ---------------------------------------------------------------------------
# Benchmark mode (requires real model)
# ---------------------------------------------------------------------------

def run_benchmark(cases_dir, model="opus", adapter=None, save_dir=None,
                   prompt_depth="deep"):
    """Run eval cases with a real model adapter.

    adapter: ModelAdapter instance.  If None, uses ClaudeCliAdapter.
    save_dir: directory to save model responses (default: cases_dir/../responses/).
    prompt_depth: 'deep' or 'shallow' — selects which prompt template to use.
    """
    from cold_eyes.claude import ClaudeCliAdapter
    from cold_eyes.prompt import build_prompt_text

    if adapter is None:
        adapter = ClaudeCliAdapter()
    if save_dir is None:
        save_dir = os.path.join(os.path.dirname(cases_dir), "responses")
    os.makedirs(save_dir, exist_ok=True)

    cases = load_cases(cases_dir)
    prompt_text = build_prompt_text(depth=prompt_depth)
    results = []

    for case in cases:
        diff = case["diff"]
        if not diff.strip():
            results.append({
                "id": case["id"],
                "category": case["category"],
                "expected_block": case["ground_truth"]["should_block"],
                "actual_block": False,
                "match": not case["ground_truth"]["should_block"],
                "model_response": None,
                "skipped": True,
            })
            continue

        invocation = adapter.review(diff, prompt_text, model)
        raw_response = invocation.stdout or ""

        # Save response
        resp_path = os.path.join(save_dir, f"{case['id']}_response.json")
        with open(resp_path, "w", encoding="utf-8") as f:
            f.write(raw_response)

        # Parse and evaluate
        review = parse_review_output(raw_response)
        outcome = apply_policy(
            review, mode="block", threshold="critical", allow_once=False,
            min_confidence="medium",
        )

        gt = case["ground_truth"]
        actual_block = outcome["action"] == "block"

        results.append({
            "id": case["id"],
            "category": case["category"],
            "expected_block": gt["should_block"],
            "actual_block": actual_block,
            "match": actual_block == gt["should_block"],
            "model_response": review,
        })

    passed = sum(1 for r in results if r["match"])
    return _make_report({
        "mode": "benchmark",
        "model": model,
        "prompt_depth": prompt_depth,
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "cases": results,
    })


# ---------------------------------------------------------------------------
# Report formatting, saving, comparison
# ---------------------------------------------------------------------------

def format_markdown(report):
    """Format a report as markdown string."""
    mode = report.get("mode", "unknown")
    lines = [
        f"# Cold Eyes Eval Report — {mode}",
        "",
        f"- **Version:** {report.get('cold_eyes_version', 'unknown')}",
        f"- **Timestamp:** {report.get('timestamp', 'unknown')}",
        f"- **Eval Schema Version:** {report.get('eval_schema_version', 'unknown')}",
        "",
    ]

    if mode == "deterministic":
        lines += [
            "## Results",
            "",
            f"- **Threshold:** {report.get('threshold', '-')}",
            f"- **Confidence:** {report.get('confidence', '-')}",
            f"- **Total:** {report['total']} | **Passed:** {report['passed']} | **Failed:** {report['failed']}",
            "",
            "### Cases",
            "",
            "| ID | Category | Expected | Actual | Match |",
            "|---|---|---|---|---|",
        ]
        for c in report.get("cases", []):
            exp = "block" if c["expected_block"] else "pass"
            act = c.get("actual_action", "block" if c.get("actual_block") else "pass")
            match_sym = "\u2713" if c["match"] else "\u2717"
            lines.append(f"| {c['id']} | {c['category']} | {exp} | {act} | {match_sym} |")

        # Category summary
        by_cat = {}
        for c in report.get("cases", []):
            cat = c["category"]
            by_cat.setdefault(cat, {"total": 0, "passed": 0})
            by_cat[cat]["total"] += 1
            if c["match"]:
                by_cat[cat]["passed"] += 1
        lines += [
            "",
            "### Category Summary",
            "",
            "| Category | Total | Passed | Rate |",
            "|---|---|---|---|",
        ]
        for cat in sorted(by_cat):
            t = by_cat[cat]["total"]
            p = by_cat[cat]["passed"]
            rate = f"{p/t*100:.0f}%" if t > 0 else "-"
            lines.append(f"| {cat} | {t} | {p} | {rate} |")

    elif mode == "sweep":
        lines += [
            "## Threshold Sweep",
            "",
            "| Threshold | Confidence | Precision | Recall | F1 |",
            "|---|---|---|---|---|",
        ]
        for s in report.get("sweep", []):
            lines.append(f"| {s['threshold']} | {s['confidence']} | {s['precision']:.4f} | {s['recall']:.4f} | {s['f1']:.4f} |")
        rec = report.get("recommended", {})
        if rec:
            lines += [
                "",
                f"**Recommended:** threshold={rec['threshold']}, confidence={rec['confidence']} (F1={rec['f1']:.4f})",
            ]

    elif mode == "benchmark":
        lines += [
            "## Benchmark Results",
            "",
            f"- **Model:** {report.get('model', '-')}",
            f"- **Total:** {report['total']} | **Passed:** {report['passed']} | **Failed:** {report['failed']}",
            "",
            "| ID | Category | Expected | Actual | Match |",
            "|---|---|---|---|---|",
        ]
        for c in report.get("cases", []):
            exp = "block" if c["expected_block"] else "pass"
            act = "block" if c.get("actual_block") else "pass"
            match_sym = "\u2713" if c["match"] else "\u2717"
            lines.append(f"| {c['id']} | {c['category']} | {exp} | {act} | {match_sym} |")

    return "\n".join(lines) + "\n"


def save_report(report, output_dir=None, fmt="json"):
    """Save report to output_dir.  fmt: json, markdown, or both."""
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(output_dir, exist_ok=True)

    mode = report.get("mode", "unknown")
    ts = report.get("timestamp", "")
    # 20260412T123456Z → safe filename segment
    ts_safe = ts.replace(":", "").replace("-", "").split(".")[0]
    base = f"{mode}_{ts_safe}"

    paths = {}
    if fmt in ("json", "both"):
        p = os.path.join(output_dir, f"{base}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        paths["json"] = p
    if fmt in ("markdown", "both"):
        p = os.path.join(output_dir, f"{base}.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(format_markdown(report))
        paths["markdown"] = p
    return paths


def regression_check(baseline_path, cases_dir, threshold="critical", confidence="medium"):
    """Run deterministic eval and compare against a saved baseline.

    Return dict with regressed (bool) and details (list of regressions).
    A regression = a case that matched in baseline but fails now.
    """
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)

    current = run_deterministic(cases_dir, threshold=threshold, confidence=confidence)
    diff = compare_reports(baseline, current)

    regressions = []
    for change in diff.get("cases_changed", []):
        # Regression: was matching (match_a=True) but now fails (match_b=False)
        if change.get("match_a") is True and change.get("match_b") is False:
            regressions.append(change)

    return {
        "regressed": len(regressions) > 0,
        "regressions": regressions,
        "baseline_version": baseline.get("cold_eyes_version"),
        "current_version": current.get("cold_eyes_version"),
        "baseline_passed": baseline.get("passed"),
        "baseline_total": baseline.get("total"),
        "current_passed": current.get("passed"),
        "current_total": current.get("total"),
        "cases_added": diff.get("cases_added", []),
        "cases_removed": diff.get("cases_removed", []),
    }


def compare_reports(report_a, report_b):
    """Compare two reports.  Return dict with differences."""
    result = {
        "version_a": report_a.get("cold_eyes_version"),
        "version_b": report_b.get("cold_eyes_version"),
        "timestamp_a": report_a.get("timestamp"),
        "timestamp_b": report_b.get("timestamp"),
    }

    cases_a = {c["id"]: c for c in report_a.get("cases", [])}
    cases_b = {c["id"]: c for c in report_b.get("cases", [])}
    ids_a = set(cases_a)
    ids_b = set(cases_b)

    result["cases_added"] = sorted(ids_b - ids_a)
    result["cases_removed"] = sorted(ids_a - ids_b)

    changed = []
    for cid in sorted(ids_a & ids_b):
        a, b = cases_a[cid], cases_b[cid]
        if a.get("match") != b.get("match") or a.get("actual_block") != b.get("actual_block"):
            changed.append({
                "id": cid,
                "match_a": a.get("match"),
                "match_b": b.get("match"),
                "action_a": a.get("actual_action", "block" if a.get("actual_block") else "pass"),
                "action_b": b.get("actual_action", "block" if b.get("actual_block") else "pass"),
            })
    result["cases_changed"] = changed

    # F1 comparison for sweep reports
    if report_a.get("mode") == "sweep" and report_b.get("mode") == "sweep":
        rec_a = report_a.get("recommended", {})
        rec_b = report_b.get("recommended", {})
        result["f1_a"] = rec_a.get("f1")
        result["f1_b"] = rec_b.get("f1")
        if rec_a.get("f1") is not None and rec_b.get("f1") is not None:
            result["f1_delta"] = round(rec_b["f1"] - rec_a["f1"], 4)

    return result
