# History JSONL Schema (format version 2)

Cold Eyes logs every review run to `~/.claude/cold-review-history.jsonl`. Each line is a complete JSON entry.

## Entry format

```json
{
  "version": 2,
  "timestamp": "2026-04-11T08:30:45Z",
  "cwd": "/home/user/project",
  "mode": "block",
  "model": "opus",
  "state": "blocked",
  "gate_state": "blocked_issue",
  "duration_ms": 1840,
  "min_confidence": "medium",
  "scope": "working",
  "schema_version": 1,
  "override_reason": "",
  "override_note": "",
  "cold_eyes_verdict": "fail",
  "final_action": "block",
  "authority": "cold_eyes",
  "envelope": {
    "schema_version": 2,
    "tool_version": "2.0.0",
    "primary_scope": "staged",
    "shadow_scope": "working_delta",
    "review_required": true,
    "safe_only": false,
    "envelope_hash": "sha256:..."
  },
  "cache": {
    "hit": false,
    "reason": "miss"
  },
  "protection": {
    "agent_task": true,
    "user_message": true,
    "block_type": "finding_block",
    "risk_summary": ["可能有安全風險"],
    "intent": {
      "status": "found",
      "has_summary": true
    }
  },
  "coverage": {
    "status": "complete",
    "coverage_pct": 100.0,
    "reviewed_files": 3,
    "total_files": 3,
    "unreviewed_files": [],
    "unreviewed_high_risk_files": [],
    "policy": "warn",
    "action": "pass",
    "reason": ""
  },
  "checks": {
    "mode": "auto",
    "hard_failed": false,
    "results": [],
    "warnings": []
  },
  "failure_kind": null,
  "stderr_excerpt": "",
  "diff_stats": {
    "files": 3,
    "lines": 45,
    "tokens": 890,
    "truncated": false
  },
  "review": { "...full review object..." },
  "reason": ""
}
```

## Field reference

| Field | Type | Always present | Description |
|-------|------|---------------|-------------|
| `version` | int | Yes | Entry schema version (always 2) |
| `timestamp` | string | Yes | ISO 8601 UTC |
| `cwd` | string | Yes | Working directory at review time |
| `mode` | string | Yes | `block`, `report`, or `off` |
| `model` | string | Yes | Model used (`opus`, `sonnet`, `haiku`) |
| `state` | string | Yes | One of 6 outcome states (see below) |
| `gate_state` | string | New entries | Authoritative v2 gate state (see below) |
| `duration_ms` | int | New entries | End-to-end review duration in milliseconds |
| `min_confidence` | string | Yes | Confidence threshold used (`high`, `medium`, `low`) |
| `scope` | string | Yes | Diff scope (`working`, `staged`, `head`, `pr-diff`) |
| `schema_version` | int | Yes | Model review output schema version (currently 1) |
| `override_reason` | string | When overridden | Reason text from override token |
| `override_note` | string | When supplied | Optional human note attached to override |
| `cold_eyes_verdict` | string | New entries | Original reviewer verdict: `pass`, `fail`, `incomplete`, `infra_failed` |
| `final_action` | string | New entries | Final disposition: `pass`, `report`, `block`, `override_pass`, `coverage_block`, `check_block`, `target_block`, `unreviewed_delta_block`, `stale_review_block`, `infra_block`, `lock_block` |
| `authority` | string | New entries | Decision authority: `cold_eyes`, `human_override`, `coverage_gate`, `target_sentinel`, `delta_sentinel`, `stale_review_guard`, `lock_guard`, `local_checks`, `infrastructure`, `envelope_cache` |
| `envelope` | object | New v2 entries | Compact gate-envelope summary with changed files, review target, unreviewed delta, hashes, and envelope schema version |
| `cache` | object | When cache checked | Envelope cache lookup result |
| `protection` | object | When available | Compact protection summary: whether an agent task/user message was generated, block type, risk summary, and intent capsule status |
| `target` | object | When available | Review-target summary: staged/unstaged/untracked counts, partial-stage files, high-risk unreviewed files, and target policy action |
| `coverage` | object | When coverage evaluated | Coverage gate status and unreviewed file details |
| `checks` | object | When local checks evaluated | Compact local-check summary |
| `failure_kind` | string | When infra failed | `timeout`, `cli_not_found`, `cli_error`, `empty_output` |
| `stderr_excerpt` | string | When infra failed | First 500 chars of CLI stderr |
| `diff_stats` | object | When review ran | File count, line count, token count, truncated flag |
| `review` | object/null | Yes | Full parsed review or null if no review ran |
| `reason` | string | When review is null | Why no review ran (e.g., "no changes") |

## States

| State | Meaning | When |
|-------|---------|------|
| `passed` | Review completed, no blocking issues | Normal pass |
| `blocked` | Review found issues at or above threshold | Block mode, severity >= threshold |
| `overridden` | Block was bypassed via override token | `arm-override` consumed |
| `skipped` | No review ran | No changes, all files ignored, mode off |
| `infra_failed` | Infrastructure error | CLI error, timeout, empty output, parse failure |
| `reported` | Issues found but not blocked | Report mode with issues |

## Gate states

`gate_state` is the authoritative v2 protection state. The legacy `state` field stays stable for existing stats, dashboards, and history readers.

| Gate state | Meaning |
|------------|---------|
| `protected` | Review completed and the current envelope is protected |
| `protected_cached` | Matching trusted protected envelope was reused without another model call |
| `skipped_no_change` | No relevant file changes; no model call |
| `skipped_safe` | Docs/generated/image-only envelope skipped safely; no model call by default |
| `blocked_issue` | Model finding, coverage gate, or hard local check blocked |
| `blocked_unreviewed_delta` | Source/config/test/migration delta could not be reviewed within policy |
| `blocked_stale_review` | Files changed during review, so the old review cannot protect the new envelope |
| `blocked_infra` | Review was required but the review infrastructure failed |
| `blocked_lock_active` | Another review held the lock while changed source/config needed review |
| `off_explicit` | `mode: off` was explicitly set and recorded |

## diff_stats object

Present only when a model review was actually executed (not for skipped/infra_failed entries where the model was never called).

| Field | Type | Description |
|-------|------|-------------|
| `files` | int | Number of files in the reviewed diff |
| `lines` | int | Total line count of diff text |
| `tokens` | int | Estimated token count (len/4 heuristic) |
| `truncated` | bool | True if diff exceeded token budget |

## coverage object

Present when the engine reached diff construction and could evaluate review coverage.

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `complete`, `partial`, or `insufficient` |
| `coverage_pct` | number | Percentage of candidate files fully reviewed |
| `reviewed_files` | int | Files fully included in the model diff |
| `total_files` | int | Candidate files after filtering and ranking |
| `unreviewed_files` | array | Partial, budget-skipped, binary, or unreadable files |
| `unreviewed_high_risk_files` | array | Unreviewed files matching high-risk path patterns |
| `minimum_coverage_pct` | int/null | Configured minimum |
| `policy` | string | `warn`, `block`, or `fail-closed` |
| `action` | string | Coverage decision: `pass`, `warn`, or `block` |
| `reason` | string | Machine-readable reason, such as `coverage_below_minimum` |

## target object

Present when the engine can inspect the current git target.

| Field | Type | Description |
|-------|------|-------------|
| `scope` | string | Configured review scope |
| `review_file_count` | int | Files included in the configured review target |
| `staged_count` | int | Staged changed files after ignore filtering |
| `unstaged_count` | int | Unstaged changed files after ignore filtering |
| `untracked_count` | int | Untracked files after ignore filtering |
| `partial_stage_count` | int | Files with both staged and unstaged changes |
| `unreviewed_count` | int | Files outside the configured review target |
| `high_risk_unreviewed_count` | int | Unreviewed files matching high-risk path patterns |
| `target_integrity` | string | `clean`, `dirty`, `partial`, or `empty` |
| `policy_action` | string | Target policy decision: `pass`, `warn`, or `block` |
| `policy_reason` | string | Machine-readable reason, such as `partial_stage` |

## envelope object

Present for v2 gate runs when the engine can inspect git state. This object is compact and history-safe; it does not store full diffs or file contents.

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Gate-envelope schema version, currently `2` |
| `tool_version` | string | Cold Eyes package version used to compute the envelope |
| `head_sha` | string | Current `HEAD` commit |
| `policy_hash` | string | Hash of effective policy inputs that affect gate decisions |
| `ignore_hash` | string | Hash of `.cold-review-ignore` |
| `prompt_hash` | string | Hash of review prompt files |
| `primary_scope` | string | Configured review scope, usually `staged` |
| `shadow_scope` | string | Shadow delta mode, usually `working_delta` |
| `changed_files` | object | Staged, unstaged, untracked, generated, binary, and safe file lists |
| `review_target` | object | Files selected for review, including shadow delta files when allowed |
| `unreviewed` | object | Delta files not reviewed and why (`budget`, `too_large`, `binary`, `unsupported`) |
| `review_required` | bool | Whether source/config/test/migration changes require model review |
| `safe_only` | bool | Whether the changed files were docs/generated/image-only |
| `envelope_hash` | string | Stable hash used for cache and stale-review decisions |

## cache object

Present when envelope cache lookup ran.

| Field | Type | Description |
|-------|------|-------------|
| `hit` | bool | Whether a matching envelope was found |
| `reason` | string | Cache miss/hit reason |
| `gate_state` | string | Gate state from the matched history entry, when available |
| `timestamp` | string | Timestamp of the matched history entry, when available |

## checks object

Present when the unified v2 engine evaluates local checks.

| Field | Type | Description |
|-------|------|-------------|
| `mode` | string | `auto` or `off` |
| `hard_failed` | bool | Whether a hard local check clearly failed |
| `results` | array | Compact result list with `check_id`, `status`, `blocking`, `duration_ms`, `finding_count`, and `infrastructure` |
| `warnings` | array | Tool-missing, timeout, or other non-blocking local-check warnings |

## protection object

Present when Cold Eyes attached a non-engineer protection brief or recorded intent capsule status. This is a compact history summary. The full `FinalOutcome.protection` object can include `rerun_protocol`, but history does not store the step list because Cold Eyes does not use previous block records as repair memory.

| Field | Type | Description |
|-------|------|-------------|
| `agent_task` | bool | Whether the block produced an agent-facing repair task |
| `user_message` | bool | Whether the block produced a plain-language message for the agent to relay |
| `block_type` | string | `finding_block`, `coverage_block`, `check_block`, `unreviewed_delta_block`, `stale_review_block`, `infra_block`, `lock_block`, `intent_mismatch`, or `incomplete_review` |
| `risk_summary` | array | Short non-engineer risk labels |
| `intent.status` | string | Intent capsule status, such as `found`, `missing_transcript`, `disabled`, or `skipped_budget` |
| `intent.has_summary` | bool | Whether a user-goal summary was recorded |

## review object

When present, the review object follows the schema defined in `cold_eyes/schema.py`:

```json
{
  "schema_version": 1,
  "review_status": "completed",
  "pass": false,
  "summary": "SQL injection vulnerability",
  "issues": [
    {
      "check": "SQL injection via concatenation",
      "verdict": "User input directly in query",
      "fix": "Use parameterized queries",
      "severity": "critical",
      "confidence": "high",
      "category": "security",
      "file": "db.py",
      "line_hint": "14"
    }
  ]
}
```

## Example entries by state

### passed
```json
{"version":2,"timestamp":"2026-04-11T08:30:45Z","cwd":"/home/user/project","mode":"block","model":"opus","state":"passed","gate_state":"protected","duration_ms":1840,"min_confidence":"medium","scope":"staged","schema_version":1,"diff_stats":{"files":2,"lines":30,"tokens":450,"truncated":false},"envelope":{"schema_version":2,"primary_scope":"staged","shadow_scope":"working_delta","review_required":true,"safe_only":false,"envelope_hash":"sha256:..."},"review":{"schema_version":1,"review_status":"completed","pass":true,"issues":[],"summary":"Clean changes"}}
```

### blocked
```json
{"version":2,"timestamp":"2026-04-11T08:31:12Z","cwd":"/home/user/project","mode":"block","model":"opus","state":"blocked","gate_state":"blocked_issue","duration_ms":2310,"min_confidence":"medium","scope":"staged","schema_version":1,"diff_stats":{"files":1,"lines":8,"tokens":120,"truncated":false},"review":{"schema_version":1,"review_status":"completed","pass":false,"issues":[{"check":"Hardcoded secret","verdict":"API key in source","fix":"Use env variable","severity":"critical","confidence":"high","category":"security","file":"config.py","line_hint":"5"}],"summary":"Hardcoded API key"}}
```

### skipped
```json
{"version":2,"timestamp":"2026-04-11T08:32:00Z","cwd":"/home/user/project","mode":"block","model":"opus","state":"skipped","gate_state":"skipped_no_change","min_confidence":"medium","scope":"staged","schema_version":1,"reason":"no relevant changes","review":null}
```

### infra_failed
```json
{"version":2,"timestamp":"2026-04-11T08:33:15Z","cwd":"/home/user/project","mode":"block","model":"opus","state":"blocked","gate_state":"blocked_infra","min_confidence":"medium","scope":"staged","schema_version":1,"failure_kind":"timeout","stderr_excerpt":"Error: request timed out after 300s","reason":"Cold Eyes could not verify a review-required change: claude exit -1","review":null}
```

## Migration notes

### History format v1 to v2

- v1 entries (from v0.10.x and earlier) have `"version": 1` or no version field
- History format v1 used `"state": "failed"` for infrastructure failures; format v2 uses `"infra_failed"`
- v1 did not have `min_confidence`, `scope`, `failure_kind`, `stderr_excerpt`
- v2.0.0 entries may add `gate_state`, `envelope`, and `cache`; older entries without them remain readable
- The `status`, `stats`, and `quality-report` commands handle both history format v1 and v2 entries
