# History JSONL Schema (v2)

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
  "duration_ms": 1840,
  "min_confidence": "medium",
  "scope": "working",
  "schema_version": 1,
  "override_reason": "",
  "override_note": "",
  "cold_eyes_verdict": "fail",
  "final_action": "block",
  "authority": "cold_eyes",
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
| `duration_ms` | int | New entries | End-to-end review duration in milliseconds |
| `min_confidence` | string | Yes | Confidence threshold used (`high`, `medium`, `low`) |
| `scope` | string | Yes | Diff scope (`working`, `staged`, `head`, `pr-diff`) |
| `schema_version` | int | Yes | Review output schema version (currently 1) |
| `override_reason` | string | When overridden | Reason text from override token |
| `override_note` | string | When supplied | Optional human note attached to override |
| `cold_eyes_verdict` | string | New entries | Original reviewer verdict: `pass`, `fail`, `incomplete`, `infra_failed` |
| `final_action` | string | New entries | Final disposition: `pass`, `report`, `block`, `override_pass`, `coverage_block`, `check_block` |
| `authority` | string | New entries | Decision authority: `cold_eyes`, `human_override`, `coverage_gate`, `local_checks`, `infrastructure` |
| `protection` | object | When available | Compact protection summary: whether an agent task/user message was generated, block type, risk summary, and intent capsule status |
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

## checks object

Present when the unified v1 engine evaluates local checks.

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
| `block_type` | string | `finding_block`, `coverage_block`, `check_block`, `intent_mismatch`, or `incomplete_review` |
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
{"version":2,"timestamp":"2026-04-11T08:30:45Z","cwd":"/home/user/project","mode":"block","model":"opus","state":"passed","duration_ms":1840,"min_confidence":"medium","scope":"working","schema_version":1,"diff_stats":{"files":2,"lines":30,"tokens":450,"truncated":false},"review":{"schema_version":1,"review_status":"completed","pass":true,"issues":[],"summary":"Clean changes"}}
```

### blocked
```json
{"version":2,"timestamp":"2026-04-11T08:31:12Z","cwd":"/home/user/project","mode":"block","model":"opus","state":"blocked","duration_ms":2310,"min_confidence":"medium","scope":"staged","schema_version":1,"diff_stats":{"files":1,"lines":8,"tokens":120,"truncated":false},"review":{"schema_version":1,"review_status":"completed","pass":false,"issues":[{"check":"Hardcoded secret","verdict":"API key in source","fix":"Use env variable","severity":"critical","confidence":"high","category":"security","file":"config.py","line_hint":"5"}],"summary":"Hardcoded API key"}}
```

### skipped
```json
{"version":2,"timestamp":"2026-04-11T08:32:00Z","cwd":"/home/user/project","mode":"block","model":"opus","state":"skipped","min_confidence":"medium","scope":"working","schema_version":1,"reason":"no changes","review":null}
```

### infra_failed
```json
{"version":2,"timestamp":"2026-04-11T08:33:15Z","cwd":"/home/user/project","mode":"block","model":"opus","state":"infra_failed","min_confidence":"medium","scope":"working","schema_version":1,"failure_kind":"timeout","stderr_excerpt":"Error: request timed out after 300s","reason":"claude exit -1","review":null}
```

## Migration notes

### v1 to v2

- v1 entries (from v0.10.x and earlier) have `"version": 1` or no version field
- v1 used `"state": "failed"` for infrastructure failures; v2 uses `"infra_failed"`
- v1 did not have `min_confidence`, `scope`, `failure_kind`, `stderr_excerpt`
- The `stats` and `quality-report` commands handle both v1 and v2 entries
