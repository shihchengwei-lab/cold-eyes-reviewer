# Trust Model

How Cold Eyes works, what it can and cannot catch, and how to verify.

## What Cold Eyes is

A diff-centered second-pass gate. It reads a git diff and produces a block/pass verdict. The diff is the primary input. On the deep path it also pulls limited, structured supporting context — recent commit messages and co-changed files from git history — plus regex-based detector hints, to reduce obvious blind spots. When Claude Code hook metadata exposes a transcript path, it may add a small low-weight user-intent capsule. That capsule cannot override diff evidence and intent findings without concrete diff evidence do not block. Cold Eyes still has no requirements spec and no access to the full codebase beyond what bounded context surfaces.

It is not an AI code reviewer in the general sense. It is a **risk gate** that catches surface-level issues visible in a single diff.

## What it can detect

Issues that a human reviewer would catch by reading the diff alone, without needing to understand intent or full project context:

| Category | Examples |
|---|---|
| Security | SQL injection via string concatenation, hardcoded credentials, XSS from unescaped output, path traversal, eval() on user input |
| Correctness | Removed error handling, unclosed resources, dangling imports after deletion, partial state updates |
| Consistency | Text contradicting nearby text within the same diff |
| Reference | Deleted function still referenced in the same diff |
| Complexity | Copy-paste patterns visible in the diff |

These are the six check items defined in the system prompt (`cold-review-prompt.txt`).

## What it cannot detect

| Gap | Why |
|---|---|
| Business logic errors | Requires understanding intent and requirements |
| Requirement violations | The optional intent capsule is only a weak hint, not a requirements spec |
| Cross-file issues not in diff | Only files in the diff are visible |
| Subtle algorithmic bugs | Requires reasoning beyond diff surface |
| Race conditions / timing issues | Rarely visible in a single diff |
| Architectural problems | Requires full codebase understanding |
| Style preferences | Explicitly excluded from the prompt |
| Domain-specific correctness | Prompt instructs: "不確定就不報" |

## Trust properties

**Deterministic post-filter.** The confidence filter and policy decision are deterministic Python code. Given the same model output, the same block/pass decision always results. The eval framework tests this boundary.

**Non-deterministic model.** The LLM review itself is non-deterministic. Different runs on the same diff may produce different issues. The benchmark eval mode measures real model behavior; the deterministic mode tests only the decision boundary.

**Fail-closed when review is required.** In block mode, infrastructure failures (CLI timeout, parse error, empty output) produce `blocked_infra` when source/config changes need review. No-change, safe-only, and cache-hit paths do not manufacture a block. The `failure_kind` field in history records the cause. This is configurable via `infra_failure_policy`.

**No silent source/config delta pass.** The v2 envelope scans unstaged and untracked source/config changes even when `scope: staged` remains the primary review intent. Reviewable shadow delta is included; high-risk, too-large, unreadable, binary, or over-budget delta blocks as `blocked_unreviewed_delta`.

**No network.** All external communication happens through local subprocess calls to `git` and `claude` CLI. No HTTP, no API keys, no outbound connections from Cold Eyes itself.

**No repair memory.** Review history is an append-only JSONL file for diagnostics, auto-tune, and override false-positive calibration. Cold Eyes does not store pending block state, remember "what it blocked last time," or validate a fix against the previous block.

**No code execution.** Cold Eyes never generates, modifies, or executes code. It reads diffs and produces JSON verdicts.

**Agent-first block output.** When Cold Eyes blocks, it can package the result as an agent repair task, a plain-language message for the agent to relay to the user, and a rerun protocol. The rerun protocol belongs to the main agent: fix the current diff, run relevant checks, then end the turn so the next Stop hook starts a fresh Cold Eyes review. This packaging does not change the underlying pass/block decision.

## Blocking direction

Cold Eyes is tuned as a low-friction gate: critical issues block, major issues are reported but pass by default. Real-model benchmark runs may surface issues without blocking them when the reviewer labels them below the configured threshold. The user's knobs:

- **Threshold** (`critical` / `major`) — higher threshold means fewer blocks, more risk that detected major issues are reported but allowed through
- **Confidence** (`high` / `medium` / `low`) — higher confidence means fewer blocks from uncertain findings
- **Override** (`arm-override`) — escape hatch for known-good code that triggers a false positive

See `docs/assurance-matrix.md` for per-category FP/FN analysis.

## Verification

Anyone can verify Cold Eyes' decision boundary locally:

```bash
# Deterministic eval — tests parse + policy against 33 cases
python cold_eyes/cli.py eval --eval-mode deterministic

# Threshold sweep — precision/recall/F1 across all threshold × confidence combos
python cold_eyes/cli.py eval --eval-mode sweep

# Benchmark (requires Claude CLI) — sends real diffs to model
python cold_eyes/cli.py eval --eval-mode benchmark --model opus
```

The eval corpus is at `evals/cases/` with schema at `evals/schema.md` and manifest at `evals/manifest.json`. See `docs/evaluation.md` for details.

## Known gaps

- **`line_hint` accuracy unmeasured.** Line references are LLM estimates from diff hunk headers. Block messages display `~` prefix. Hallucination rate is not formally measured.
- **Token estimation is approximate.** `len(encode("utf-8")) ÷ 4` is closer than `len ÷ 4` for CJK but still a heuristic.
- **No cross-file analysis.** If a function is deleted in file A and referenced in file B, Cold Eyes only catches this if both files are in the diff.
- **Eval corpus is minimal.** 33 cases test the decision boundary. Real-world accuracy depends on model behavior, which varies by model and prompt.
- **No intent understanding.** Cold Eyes cannot distinguish "intentionally removed error handling" from "accidentally removed error handling."
