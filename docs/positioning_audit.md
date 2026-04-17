# Positioning Audit

Baseline inventory before the narrow-positioning documentation pass. Compiled from a repo-wide scan for outward-facing copy that describes what Cold Eyes is, is not, or does.

**Target positioning** (one sentence):

> Cold Eyes is a diff-centered, second-pass gate for Claude Code. It reviews the current change primarily through the diff, and in deeper paths may use limited, structured supporting context. It is not a full code review system and does not claim full intent understanding.

---

## 1. Problematic phrases — verbatim hits

Each row is a line that currently over-narrows the positioning (implying the tool is diff-only / zero-context) or is out of alignment with the deep path's actual behaviour.

| # | File:Line | Current wording (verbatim) | Problem |
|---|---|---|---|
| P1 | `pyproject.toml:8` | `description = "Zero-context code review engine for Claude Code Stop hooks"` | Absolute "Zero-context" denies deep-path context loading |
| P2 | `cold_eyes/__init__.py:1` | `"""Cold Eyes Reviewer — zero-context code review engine."""` | Same as P1; propagates to every `import cold_eyes` |
| P3 | `cold_eyes/prompt.py:42` | `"You are Cold Eyes, a zero-context reviewer. Review the diff. Output JSON..."` | Fallback prompt string (only used if template file missing); still misframes disposition |
| P4 | `README.md:9` | `"It has no conversation context and no requirements. ... Shallow reviews see only the diff."` | "has no ... context" + "only the diff" — absolute wording; deep path does load bounded context |
| P5 | `docs/trust-model.md:7` | `"A zero-context second-pass gate. It reads a git diff and produces a block/pass verdict. It sees only the diff — no conversation, no project history, no requirements, no full codebase."` | Flat denial of context; contradicts deep path + detector hints |
| P6 | `docs/assurance-matrix.md:14` | `"Inherently limited by zero-context design"` (in `consistency` category row) | Calls the tool "zero-context" as if it were the design principle |
| P7 | `docs/assurance-matrix.md:49` | `"What zero-context review cannot do, and workarounds where they exist."` | Same issue as P6 |
| P8 | `tests/test_shallow_and_context.py:31` | `assert "邏輯錯誤" in text or "zero-context" in text.lower()` | OR-fallback assert; CJK clause currently satisfies it so test passes, but the fallback anchors the wrong term |
| P9 | `CHANGELOG.md:183` | `shallow reviews as diff-only.` (v1.9.0 historical note) | Historical record — **do not rewrite**. Noted here for completeness. |

**Correct negation retained (do not remove):**

- `docs/trust-model.md:9` — `"It is not an AI code reviewer in the general sense. It is a **risk gate** that catches surface-level issues visible in a single diff."` — this is a correct narrow-positioning sentence.

---

## 2. Structural gaps in `README.md`

Current README heading order:

```
# Cold Eyes Reviewer
## How it works
## Output format
## Install
## Token usage
## What gets reviewed
## Configuration
## Failure modes
## Requirements
## Files
## Building on top of Cold Eyes
## Diagnostics
## Known limitations
## Uninstall
## Contributing
## Security
## License
```

**Missing dedicated sections** (per roadmap §1.2 and §2):

- No `What it is` (positioning is embedded in the paragraph at L9)
- No `What it is not`
- No `When it works best` / `Best-fit scenarios`
- No `When not to use it as a blocking gate` / `Poor-fit scenarios`
- `Recommended adoption path` exists at L141 but is procedural (report-only → threshold tuning), not positioning-facing.

The first ~200 words of README currently lead with architectural diagram (`How it works`) rather than with what-it-is / what-it-is-not. A first-time reader cannot answer "should I try this" in 2 minutes from the top of the file.

---

## 3. Capabilities that exist (must not be denied in rewrite)

Verified against the code. Each capability has a file:line anchor; use these when writing the rewrite to avoid denying real features.

| Capability | Exists | Anchor | One-line summary |
|---|---|---|---|
| shallow / deep / v2 review paths | Yes | `cold_eyes/triage.py:46-112` (`classify_depth`); `cold_eyes/engine.py:171-172`; `cold_eyes/cli.py:168,250` | Triage picks skip/shallow/deep; `--v2` CLI flag opts into v2 session pipeline |
| Bounded context ingestion (deep path) | Yes | `cold_eyes/context.py:32-86` (`build_context`); invoked at `cold_eyes/engine.py:206-212` | Deep path loads recent commits + co-changed files, token-capped (default 2000) |
| Detector hints | Yes | `cold_eyes/detector.py:141-179` (`build_detector_hints`); appended at `cold_eyes/engine.py:216-226` | Regex state/invariant signals + repo-type focus checks, deep path only |
| Input composition order | Yes | `cold_eyes/engine.py:210,221` | diff → context → hints |
| Session persistence (v2) | Yes | `cold_eyes/session/store.py:9-41` | JSONL at `~/.claude/cold-review-sessions/sessions.jsonl` |
| Retry machinery (v2) | Yes | `cold_eyes/retry/` (7 files: taxonomy, brief, signal_parser, translator, strategy, stop, __init__) | Failure classification → retry brief → strategy → stop conditions |
| Suppression / dedup / FP memory | Yes | `cold_eyes/noise/` (6 files: dedup, grouping, retry_suppression, fp_memory, calibration, __init__) | Cumulative dedup, FP pattern downgrade, calibration |
| Non-LLM gates | Yes | `cold_eyes/gates/catalog.py:24-80` | 5 builtins: `llm_review` (LLM) + `test_runner` / `lint_checker` / `type_checker` / `build_checker` (subprocess) |
| Cost budget controls | Yes | `cold_eyes/cli.py:131-164`; `cold_eyes/config.py:13-18`; gates `catalog.py:12` (`cost_class`) | `--max-tokens` / `--context-tokens` / `--max-input-tokens`; per-gate cost_class |
| v1 / v2 coexistence | Yes | `cold_eyes/cli.py:168,250-253` | v1 is default; v2 opt-in via `--v2`; v2 also writes v1 history for stats |

All nine capabilities are real. The rewrite's job is to describe them honestly without using absolute phrases (`zero-context`, `diff-only`, `only the diff`).

---

## 4. Docs already aligned (leave as-is)

- `docs/architecture.md` — technical architecture; no positioning claims.
- `docs/failure-modes.md` — operational reference; no positioning.
- `docs/evaluation.md` — eval framework; no positioning.
- `docs/troubleshooting.md`, `docs/tuning.md`, `docs/scope-strategy.md`, `docs/agent-setup.md` — procedural.
- `docs/roadmap.md`, `docs/alpha-scope.md`, `docs/version-policy.md`, `docs/support-policy.md`, `docs/release-checklist.md` — internal.
- `SECURITY.md`, `CONTRIBUTING.md` — non-positioning.

---

## 5. Docs that do not exist yet (to be created by this pass)

- `docs/positioning_audit.md` — **this file**
- `docs/positioning_consistency_checklist.md` — rewrite tracker, Commit 1 companion
- `docs/disclosure_matrix.md` — Commit 3
- `docs/repo_page_reveal_recommendations.md` — Commit 3
- `docs/release_note_template.md` — Commit 3

---

## 6. Replacement wording direction

Use these when rewriting P1–P8:

| Do use | Avoid |
|---|---|
| `diff-centered` | `diff-only` |
| `diff-first` | `reads only the diff` |
| `bounded supporting context` | `zero-context` |
| `limited structured supporting context` | `no context` |
| `not a full-context reviewer` | `reviews code changes without context` |
| `not intent-aware` | `understands nothing` |
| `not a replacement for full review` | `complete review framework` |
| `second-pass gate for Claude Code` | `AI code reviewer platform` |
| `opt-in deeper verification path` (for v2) | `full verification platform` |

---

## 7. Scope of the rewrite

This audit supports four commits:

1. **Commit 1** — this file + `positioning_consistency_checklist.md`. No other files touched.
2. **Commit 2** — P1–P4 + P8, README restructure.
3. **Commit 3** — the three disclosure scaffolding docs; no rewrites of existing files.
4. **Commit 4** — P5–P7, version bump to v1.11.4, CHANGELOG entry, HANDOVER sync.

P9 (CHANGELOG L183) is historical and will not be rewritten.
