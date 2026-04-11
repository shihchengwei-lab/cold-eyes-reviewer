"""Eval runner — deterministic, benchmark, and sweep modes.

Deterministic mode tests the decision boundary (parse + policy) using
mock responses embedded in case files.  No git, no model calls.

Benchmark mode sends real diffs to a model and records responses.

Sweep mode replays saved responses across threshold x confidence combinations
to compute precision / recall / F1.
"""

import json
import os
import glob as _glob

# Allow running from project root
import sys
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from cold_eyes.review import parse_review_output
from cold_eyes.policy import apply_policy
from cold_eyes.constants import SEVERITY_ORDER


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

    outcome = apply_policy(
        review, mode="block", threshold=threshold, allow_once=False,
        min_confidence=confidence, truncated=truncated,
        skipped_files=skipped_files,
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
    return {
        "mode": "deterministic",
        "threshold": threshold,
        "confidence": confidence,
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "cases": results,
    }


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
    return {
        "mode": "sweep",
        "combinations": len(sweep),
        "sweep": sweep,
        "recommended": {
            "threshold": best["threshold"],
            "confidence": best["confidence"],
            "f1": best["f1"],
        },
    }


# ---------------------------------------------------------------------------
# Benchmark mode (requires real model)
# ---------------------------------------------------------------------------

def run_benchmark(cases_dir, model="opus", adapter=None, save_dir=None):
    """Run eval cases with a real model adapter.

    adapter: ModelAdapter instance.  If None, uses ClaudeCliAdapter.
    save_dir: directory to save model responses (default: cases_dir/../responses/).
    """
    from cold_eyes.claude import ClaudeCliAdapter
    from cold_eyes.prompt import build_prompt_text

    if adapter is None:
        adapter = ClaudeCliAdapter()
    if save_dir is None:
        save_dir = os.path.join(os.path.dirname(cases_dir), "responses")
    os.makedirs(save_dir, exist_ok=True)

    cases = load_cases(cases_dir)
    prompt_text = build_prompt_text()
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
    return {
        "mode": "benchmark",
        "model": model,
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "cases": results,
    }
