# Roadmap

This is a personal tool. The roadmap is directional, not committed.

## Completed Direction

### Verifiable trust baseline

- [x] Eval corpus, manifest, schema, deterministic runner, regression gate
- [x] Trust model, security trust boundaries, assurance matrix
- [x] Evidence-bound issue schema and confidence calibration
- [x] False-positive memory from override history

### Cost-effective cold review

- [x] Risk categories and file roles
- [x] Skip / shallow / deep triage
- [x] Shallow prompt and configurable shallow model
- [x] Bounded deep context from git history and detector hints
- [x] Coverage gate for incomplete or high-risk unreviewed files

### Correctness session experiment (retired)

- [x] Explored session, contract, gates, retry, noise, and runner packages
- [x] Proved local subprocess gates can be normalized into structured findings
- [x] Retired the separate `--v2` product path in favor of unified v1
- [x] Did not keep session persistence, retry loop, or prior-block validation in the default tool

### Agent-first gate hardening

- [x] Protection brief for blocks: agent task, user message, risk summary, intent metadata
- [x] Low-weight intent capsule from Stop hook metadata, never stronger than diff evidence
- [x] Fresh-review rerun protocol for the main agent
- [x] No repair memory: no pending-block store and no validation against previous block records

### Unified local checks and cleanup (v1.16.x)

- [x] Single v1 run path; hidden `--v2` compatibility falls back to v1
- [x] Risk-based automatic local checks: pytest, ruff, mypy, pip check
- [x] Hard local check failures can block; soft failures feed the Agent task
- [x] Local check results are attached to outcome and history without schema-major bump
- [x] Soft checks target changed Python files when possible to avoid unnecessary full-repo sweeps
- [x] Removed retired session, contract, retry, noise, and runner source modules after v1 absorbed the useful local-check parser

### No Silent Pass Delta Gate (v2.0.0)

- [x] Fast review envelope decides skip, cache, review, or block before model calls
- [x] Pure chat/no-change turns skip without LLM review
- [x] Matching protected envelopes reuse cache without re-review
- [x] Unstaged and untracked source/config deltas are reviewed or blocked instead of silently passing
- [x] Review-required infra failures, lock contention, stale reviews, and high-risk unreviewed delta block with explicit `gate_state`
- [x] Docs/generated/image-only changes keep a low-friction `skipped_safe` path
- [x] Retired `--v2` session engine remains retired; v2 is the unified engine behavior

## Future

- Release-by-release assurance notes
- Challenge set separate from the main benchmark
- Incident / miss postmortem template
- Head-to-head comparison framework
- Adoption profiles for solo conservative, team guardrail, and high-trust strict use
- Trust report automation from benchmark, challenge, override, and history signals

## Explicitly Out of Scope

- GUI or web dashboard
- Daemon or long-running background service
- PyPI or package registry distribution
- Multi-user or team features
- Commercial licensing or paid tiers
- Fancier prompts as the main quality lever
- More provider abstractions or integrations
