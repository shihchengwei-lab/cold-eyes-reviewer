# Eval Case Schema

Normative reference for eval case file format. Version: 1.

## Case file format

Each case is a JSON file in `evals/cases/`. Filename convention: `{prefix}_{short_name}.json`.

### Required fields

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique kebab-case identifier (e.g. `tp-sql-injection`) |
| `category` | string | One of: `true_positive`, `acceptable`, `false_negative`, `stress`, `edge` |
| `description` | string | What this case tests, one sentence |
| `diff` | string | Unified diff text. Empty string for cases with `expect_skip` |
| `mock_response` | object | Embedded model response (see below) |
| `ground_truth` | object | Expected outcome (see below) |

### Optional fields

| Field | Type | Default | Description |
|---|---|---|---|
| `settings.truncated` | bool | `false` | Simulate truncated diff |
| `settings.skipped_files` | list | `[]` | Files excluded from review |
| `settings.expect_skip` | bool | `false` | Case expects engine-level skip (e.g. empty diff) |

## mock_response format

Must match `ClaudeCliAdapter` output format:

```json
{
  "result": "<JSON string>"
}
```

The inner JSON string is parsed by `parse_review_output()`. It should contain:

| Field | Required | Default | Description |
|---|---|---|---|
| `review_status` | no | `"completed"` | `"completed"` or `"failed"` |
| `pass` | no | `true` | `true` if no blocking issues |
| `issues` | no | `[]` | Array of issue objects |
| `summary` | no | `""` | One-line summary |

Each issue object:

| Field | Required | Default |
|---|---|---|
| `check` | yes | — |
| `verdict` | yes | — |
| `fix` | yes | — |
| `severity` | no | `"major"` |
| `confidence` | no | `"medium"` |
| `category` | no | `"correctness"` |
| `file` | no | `"unknown"` |
| `line_hint` | no | `""` |

If `result` is `"{}"`, `parse_review_output` fills all defaults: `pass: true`, `issues: []`. This produces a clean pass.

## ground_truth format

| Field | Required | Description |
|---|---|---|
| `should_block` | yes | `true` if this case should trigger a block at default settings |
| `min_severity` | no | Minimum severity expected (only checked when `should_block: true`) |

**Default settings** for ground truth evaluation: `threshold=critical`, `confidence=medium`.

## Category definitions

| Category | Prefix | Meaning | Expected ground truth |
|---|---|---|---|
| `true_positive` | `tp_` | Real issues Cold Eyes should catch and block | `should_block: true` |
| `acceptable` | `ok_` | Clean changes that should pass without issues | `should_block: false` |
| `false_negative` | `fn_` | Changes that look risky but are actually acceptable | `should_block: false` |
| `stress` | `stress_` | Boundary conditions: empty diff, truncation, binary, threshold edges | varies |
| `edge` | `edge_` | Encoding, CJK, unicode, malformed output, config-only changes | varies |

## Manifest

`evals/manifest.json` indexes all cases by category. It is hand-maintained alongside case files and validated by tests. The manifest is not required by `load_cases()` — it provides a categorical overview for documentation and CI validation.

## Adding a new case

1. Create `evals/cases/{prefix}_{short_name}.json` following the schema above
2. Choose the correct category and prefix
3. Write a realistic diff and a plausible mock_response
4. Set ground_truth based on what the default policy (critical/medium) should decide
5. Add the case ID to the appropriate category in `evals/manifest.json`
6. Update `manifest.json` counts and `ground_truth_summary`
7. Run `python cold_eyes/cli.py eval --eval-mode deterministic` to verify
8. Update test assertions if case count changed
