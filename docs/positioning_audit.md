# Positioning Audit

Current target positioning:

> Cold Eyes is a diff-centered, second-pass gate for Claude Code. It reviews the current change primarily through the staged diff, scans source/config working-tree delta so it cannot silently pass, may use limited structured supporting context on deeper paths, and can run selected local checks in the same unified v2 flow. It is not a full code review system and does not claim full intent understanding.

## Current Capabilities

| Capability | Status | Anchor | Summary |
|---|---|---|---|
| Skip / shallow / deep triage | Active | `cold_eyes/triage.py` | Chooses no-model, lighter-model, or deep review path from file roles and risk categories |
| Bounded context ingestion | Active | `cold_eyes/context.py` | Deep path loads token-capped git-adjacent context |
| Detector hints | Active | `cold_eyes/detector.py` | Adds regex state/invariant and repo-type hints on deep reviews |
| Low-weight intent capsule | Active | `cold_eyes/intent.py` | Reads recent user goal from hook metadata when available; cannot block without diff evidence |
| Fresh-review rerun protocol | Active | `cold_eyes/protection.py` | Tells the main agent to fix, run checks, and end the turn for a fresh next review |
| Automatic local checks | Active | `cold_eyes/local_checks.py` | Runs selected local checks once; hard failures can block, soft failures feed Agent task |
| Review envelope / delta gate | Active | `cold_eyes/envelope.py` | Skips no-change/safe-only turns, reuses protected cache, and blocks unreviewed source/config delta |
| Session/retry pipeline | Retired and removed from active source | `cold_eyes/cli.py`, `cold_eyes/gates/result.py` | `--v2` is hidden compatibility only and falls back to the unified engine |

## Wording Direction

| Use | Avoid |
|---|---|
| `diff-centered` | `diff-only` |
| `diff-first` | `reads only the diff` |
| `bounded supporting context` | `zero-context` |
| `selected local checks` | `separate v2 pipeline` |
| `source/config delta cannot silently pass` | `full working-tree semantic review` |
| `fresh review only` | `previous block validation` |
| `second-pass gate for Claude Code` | `full code review platform` |

## Scope

This audit should be refreshed whenever the README first screen, GitHub About, release template, or default review path changes.
