# Evaluation System

Cold Eyes includes a built-in evaluation framework to measure and tune review accuracy.

## How it works

The eval system has three modes:

| Mode | What it does | Model calls |
|------|-------------|-------------|
| `deterministic` | Runs embedded mock responses through `parse_review_output` + `apply_policy` | None |
| `benchmark` | Sends real diffs to a model, records responses | Yes |
| `sweep` | Replays mock responses across threshold x confidence combinations | None |

**Deterministic** mode tests the policy decision boundary — given a model response, does the tool make the correct block/pass decision? It uses mock responses embedded in each case file, so results are fully reproducible with no model calls.

**Benchmark** mode sends actual diffs to a real model and compares the response against ground truth. Use this to evaluate model quality across different models (haiku/sonnet/opus).

**Sweep** mode runs all cases against every threshold x confidence combination (2 x 3 = 6) and computes precision, recall, and F1 for each. Use this to justify default settings.

## Running evals

```bash
# Deterministic (default, no model needed)
python cold_eyes/cli.py eval --eval-mode deterministic

# Threshold sweep
python cold_eyes/cli.py eval --eval-mode sweep

# Benchmark with real model
python cold_eyes/cli.py eval --eval-mode benchmark --model opus
```

## Eval case format

Each case is a JSON file in `evals/cases/` (see `evals/schema.md` for the formal definition):

```json
{
  "id": "unique-case-id",
  "category": "true_positive | acceptable | false_negative | stress | edge",
  "description": "What this case tests",
  "diff": "unified diff text",
  "mock_response": {
    "result": "{\"review_status\":\"completed\",\"pass\":false,\"issues\":[...],\"summary\":\"...\"}"
  },
  "ground_truth": {
    "should_block": true,
    "min_severity": "critical"
  },
  "settings": {
    "truncated": false,
    "skipped_files": []
  }
}
```

### Adding a new case

1. Create a JSON file in `evals/cases/` following the format above
2. Set `mock_response` to the expected model output (Claude CLI JSON format)
3. Set `ground_truth.should_block` based on default settings (threshold=critical, confidence=medium)
4. Run `python cold_eyes/cli.py eval` to verify
5. Run `pytest tests/test_eval.py` to check all tests still pass

All 33 cases are indexed in `evals/manifest.json` with per-category counts. `validate_manifest()` checks manifest-to-file consistency.

## Current eval set

| Category | Count | Description |
|----------|-------|-------------|
| true_positive | 10 | SQL injection, hardcoded secrets, XSS, resource leak, missing error handling, dangling import, path traversal, eval injection, state missing precheck, partial state update |
| acceptable | 4 | Variable rename, docstring update, test addition, README typo |
| false_negative | 4 | Cases that look dangerous but are acceptable (boundary testing) |
| stress | 5 | Large diff (truncation), binary-only, empty diff, mixed severity, all-minor issues |
| edge | 4 | CJK comments, unicode identifiers, empty model response, config-only changes |
| evidence | 3 | Evidence chains, abstain calibration, backward compatibility |
| fp_memory | 3 | FP pattern matching, category caps, no-match pass-through |

## Threshold sweep results

| Threshold | Confidence | Precision | Recall | F1 |
|-----------|-----------|-----------|--------|-----|
| critical | high | 1.00 | 0.88 | 0.93 |
| **critical** | **medium** | **1.00** | **1.00** | **1.00** |
| critical | low | 1.00 | 1.00 | 1.00 |
| major | high | 1.00 | 0.88 | 0.93 |
| major | medium | 1.00 | 1.00 | 1.00 |
| major | low | 1.00 | 1.00 | 1.00 |

### Why the defaults are `threshold=critical, confidence=medium`

1. **critical threshold** — Only blocks on critical-severity issues. This includes security vulnerabilities, data loss, crash bugs, and evidence-backed correctness bugs that make production runtime fail directly (for example dangling imports/references, removed required error handling, resource leaks, or partial state updates). Major issues get reported but don't block. This minimizes friction while catching the most dangerous problems.

2. **medium confidence** — Includes issues the model is moderately sure about. Setting `high` drops recall from 1.00 to 0.88 because some legitimate issues (e.g., dangling imports with indirect evidence) get confidence=medium. Setting `low` adds no benefit in this eval set but in real usage may increase false positives.

3. The deterministic `critical/medium` sweep achieves F1=1.00 on the recorded eval set with zero false positives. Real-model benchmark runs can differ because they measure the reviewer model's severity calibration, not only the post-filter policy.

### Real-model benchmark calibration

Benchmark mode sends the eval diffs to the configured model and is the best signal for prompt calibration. A v2.0.0 Opus benchmark run over the 33-case eval set passed 28/33 cases. The misses were mostly correctness issues that the model detected but labeled `major`, so the critical-only gate reported them without blocking. The prompt now explicitly tells the reviewer to classify evidence-backed dangling imports/references, removed required error handling, resource leaks, and partial state updates as `critical` when they can directly break production runtime.

### When to change defaults

- **Too many blocks?** → Raise confidence to `high` (accepts ~12% fewer true positives but eliminates uncertain calls)
- **Missing real issues?** → Lower threshold to `major` (blocks on major issues too, higher coverage but more friction)
- **Different model?** → Run `--eval-mode benchmark --model <model>` to measure actual model accuracy, then re-run sweep

## Structured pipeline

Reports from all eval modes include metadata: `cold_eyes_version`, `timestamp`, `eval_schema_version`.

```bash
# Save report as JSON + markdown
python cold_eyes/cli.py eval --save --format both

# Compare two reports
python cold_eyes/cli.py eval --save --compare evals/results/deterministic_prev.json
```

`compare_reports()` diffs two reports: cases added/removed/changed, pass/fail deltas, and F1 movement for sweep reports.

## Regression gate

`regression_check()` compares the current deterministic eval results against a saved baseline. A **regression** is any case that matched in the baseline but fails now.

### Baseline management

The canonical baseline lives at `evals/baseline.json`. It is committed to the repo and used by CI.

**Updating the baseline:**

```bash
# 1. Run deterministic eval and save
python cold_eyes/cli.py eval --save --format json

# 2. Copy the new report as the baseline
cp evals/results/deterministic_*.json evals/baseline.json

# 3. Commit the updated baseline
git add evals/baseline.json && git commit -m "eval: update baseline"
```

Update the baseline when:
- New eval cases are added (cases_added is expected)
- Policy logic changes intentionally shift pass/fail boundaries
- A model response mock is updated to reflect corrected behavior

Do **not** update the baseline to hide regressions.

### Running regression checks

```bash
# CLI — exit code 1 on regression, 0 on success
python cold_eyes/cli.py eval --regression-check evals/baseline.json

# CI runs this automatically (see .github/workflows/test.yml)
```

The output includes `regressed` (bool), `regressions` (list of changed cases), and `cases_added`/`cases_removed` for new or deleted cases.

See also: `docs/trust-model.md` (capability boundaries), `docs/assurance-matrix.md` (per-category detection ability).

## Limitations

- The deterministic eval set (33 cases) tests the decision boundary, not model quality. Add more cases as you encounter real-world false positives or missed issues.
- Stress and edge cases cover truncation, unicode, and boundary conditions but not all combinations of scope, model, and diff size.
- Precision/recall numbers reflect mock responses, not real model behavior. Use benchmark mode for model-specific evaluation.
