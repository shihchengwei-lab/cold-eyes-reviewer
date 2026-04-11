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

- **LLM responses are untrusted data.** The model output is parsed by `parse_review_output()` with JSON validation and `validate_review()` schema checks. Malformed responses trigger `infra_failed` state, not arbitrary code execution.
- **Override tokens** are file-based with TTL expiry, stored in `~/.claude/`. They grant a one-time pass for a single review cycle.
- **Policy files** (`.cold-review-policy.yml`) are flat YAML parsed by a custom parser with a fixed set of 9 valid keys. Unknown keys are silently dropped.
