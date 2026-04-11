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
  "min_confidence": "medium",
  "scope": "working",
  "schema_version": 1,
  "override_reason": "",
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
| `min_confidence` | string | Yes | Confidence threshold used (`high`, `medium`, `low`) |
| `scope` | string | Yes | Diff scope (`working`, `staged`, `head`, `pr-diff`) |
| `schema_version` | int | Yes | Review output schema version (currently 1) |
| `override_reason` | string | When overridden | Reason text from override token |
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
{"version":2,"timestamp":"2026-04-11T08:30:45Z","cwd":"/home/user/project","mode":"block","model":"opus","state":"passed","min_confidence":"medium","scope":"working","schema_version":1,"diff_stats":{"files":2,"lines":30,"tokens":450,"truncated":false},"review":{"schema_version":1,"review_status":"completed","pass":true,"issues":[],"summary":"Clean changes"}}
```

### blocked
```json
{"version":2,"timestamp":"2026-04-11T08:31:12Z","cwd":"/home/user/project","mode":"block","model":"opus","state":"blocked","min_confidence":"medium","scope":"staged","schema_version":1,"diff_stats":{"files":1,"lines":8,"tokens":120,"truncated":false},"review":{"schema_version":1,"review_status":"completed","pass":false,"issues":[{"check":"Hardcoded secret","verdict":"API key in source","fix":"Use env variable","severity":"critical","confidence":"high","category":"security","file":"config.py","line_hint":"5"}],"summary":"Hardcoded API key"}}
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
