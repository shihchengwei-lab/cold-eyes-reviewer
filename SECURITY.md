# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.2.x+  | Yes       |
| < 1.2   | No        |

## Reporting a vulnerability

To report a security issue, use [GitHub Security Advisories](https://github.com/shihchengwei-lab/cold-eyes-reviewer/security/advisories/new) (preferred) or open a regular issue if the vulnerability is not sensitive.

This is a personal project maintained on a best-effort basis. I will acknowledge reports promptly and aim to address confirmed vulnerabilities in the next patch release.

Please include:
- Cold Eyes version (`python cold_eyes/cli.py --version`)
- Steps to reproduce
- Impact assessment

## Scope

Cold Eyes Reviewer runs **locally** on the developer's machine as a Claude Code Stop hook. It:

- Executes `git` commands via subprocess to collect diffs
- Executes the `claude` CLI via subprocess to invoke the LLM
- Reads files from the current working directory
- Writes review history to `~/.claude/cold-review-history.jsonl`
- Uses `mkdir`-based file locking in `~/.claude/`

It does **not** open network connections directly, run a server, or accept remote input.

## Trust boundaries

### Input boundary

Cold Eyes receives input from two local sources only:

- **`git diff` output** — collected via subprocess. The diff content is whatever is in the git working tree. An attacker who can modify the working tree can craft diffs that trigger false positives or false negatives. This is by design — the reviewer's input IS the working tree.
- **`claude` CLI response** — collected via subprocess stdout. The response is treated as untrusted (see below).

No network input, no user-provided payloads beyond what is in the git repository.

### LLM response handling

The model output is parsed by `parse_review_output()` with two layers of validation:

1. **JSON parse** — malformed JSON falls through to a safe default (`pass: true`, `review_status: failed`).
2. **Schema validation** — `validate_review()` checks required fields, valid severity/confidence/category values. Unknown fields are ignored (forward-compatible). Invalid structure triggers `infra_failed` state, not code execution.

Cold Eyes never `eval()`s, `exec()`s, or dynamically imports anything from model output.

### Policy file parsing

`.cold-review-policy.yml` is parsed by a custom flat-YAML parser (no PyYAML dependency):

- 9 valid keys, fixed set
- 50 content-line limit (non-blank, non-comment lines only)
- Unknown keys silently dropped
- No code execution, no nested structures
- Exceeding the line limit triggers a stderr warning; already-parsed entries are preserved

### Override tokens

- File-based in `~/.claude/`, TTL-bound (default 10 minutes), single-use
- Consumed on first review cycle after creation
- Cannot be created remotely — requires local CLI access

### No code generation or execution

Cold Eyes never generates, modifies, or executes code. It reads diffs and produces JSON verdicts. The shell shim (`cold-review.sh`) and Python engine are the only executable components.

### Attack surface

| Vector | Status | Mitigation |
|---|---|---|
| Malicious diff content | Accepted risk | Reviewer input IS the working tree; no way to sanitize without losing function |
| LLM prompt injection via diff | Accepted risk | Model may be confused by adversarial diff content; fail-closed parser catches malformed output |
| Malicious policy file | Mitigated | Custom parser, fixed key set, 50-line limit, no code execution |
| Git command injection | Mitigated | Arguments passed as list to subprocess, not shell-interpolated |
| Tampered install path | Accepted risk | `~/.claude/scripts/` is a trusted path; if compromised, the attacker controls the reviewer |
| Race condition in file lock | Known limitation | `mkdir`-based lock with stale PID detection; less reliable on Windows Git Bash |

For the full trust model, see `docs/trust-model.md`.
