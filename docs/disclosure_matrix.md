# Disclosure Matrix

Where each fact about Cold Eyes belongs. Use this to decide what goes on the homepage, what belongs deeper, and what should never appear on a release note.

The repo has layers of audience. Each layer has a different job: the GitHub About is a glance, the README first screen is an adoption decision, the advanced docs are for operators and contributors. Facts that help one layer often clutter another.

---

## Layer rules

| Layer | Audience goal | Should disclose | Should NOT front-load |
|---|---|---|---|
| **GitHub About** (repo description + topics) | Identify what this is in one glance | `Claude Code` / `second-pass gate` / `diff-centered` / hint at deeper modes | retry taxonomy, gate internals, token budgets, suppression policies |
| **README first screen** (top ~700 words) | Adoption judgment: is this for me, what does it cost, when not to use | what it is, what it is not, best-fit, poor-fit, cost awareness, adoption path, 3-line shallow/deep/v2 overview | full architecture diagram, gate list, retry categories, override token flow, truncation policy details |
| **README advanced sections** | Technical credibility: why should I trust this, how do I tune it | How it works block, configuration keys, failure modes, diagnostics, building-on-top extension points, known limitations | internal module layout, implementation rationale, v2 internals |
| **`docs/` advanced** (`architecture.md`, `failure-modes.md`, `evaluation.md`, `tuning.md`, `trust-model.md`, `assurance-matrix.md`) | Operators, contributors, reviewers | v2 pipeline diagram, gate catalog, retry taxonomy, suppression mechanics, override token lifecycle, calibration rules, eval corpus, assurance matrix per category | (no upper bound — this is the catch-all) |
| **Release notes** (`CHANGELOG.md`) | What changed since last version | behavior changes, cost changes, context-usage changes, blocking-policy changes, migration/opt-in notes, audience ("who should care") | re-defining the product, reprinting the positioning paragraph, marketing claims |

---

## Fact-to-layer mapping

A partial index. When adding a new feature or doc, find the closest row and follow the convention.

| Fact / feature | GitHub About | README first screen | README advanced | docs/ advanced | Release notes |
|---|---|---|---|---|---|
| "Diff-centered second-pass gate for Claude Code" | yes (primary line) | yes (tagline) | — | — | — |
| "Not a full code review / not intent-aware" | yes (short) | yes (`What it is not`) | — | `trust-model.md`, `assurance-matrix.md` | only if changed |
| Shallow / deep / v2 three paths | hint only | yes (3-line overview) | `How it works` block | `architecture.md` full | when behavior changes |
| Bounded context (recent commits, co-changed files) | no | yes (part of `What it is`) | `How it works` step 6 | `trust-model.md`, `assurance-matrix.md` | when context changes |
| Detector hints (regex state/invariant, repo-type focus) | no | no | `How it works` step 7 | `architecture.md` | when logic changes |
| v2 gate catalog (5 gates) | no | no | `Files` section mentions | `architecture.md`, `tuning.md` | when gates added/removed |
| Retry taxonomy | no | no | no | `architecture.md` | when categories change |
| Suppression / dedup / FP memory | no | no | no | `architecture.md`, `tuning.md` | when suppression behavior changes |
| Override token + `arm-override` | no | no | `Configuration` → `Overriding a block` | `trust-model.md` | when TTL or scope changes |
| Token budgets and cost | no | yes (`Token usage`) | `Configuration` env vars table | `tuning.md` | when worst-case cost changes |
| Truncation policy (`warn` / `soft-pass` / `fail-closed`) | no | no | `Configuration` → `Truncation policy` | `architecture.md` | when default changes |
| `doctor` / `verify-install` diagnostics | no | no | `Diagnostics` | `troubleshooting.md` | when checks added/removed |
| Adoption path (`report` → `critical-only` → narrower) | no | yes | — | — | — |
| Policy file keys (`.cold-review-policy.yml`) | no | no | `Configuration` → `Policy file` | — | when keys added/removed |
| Session JSONL path (`~/.claude/cold-review-sessions/`) | no | no | `Building on top of Cold Eyes` | `architecture.md` | when path changes |

---

## Rules of thumb

1. **Up-layer facts do not demote down-layer facts.** Putting "diff-centered" on GitHub About does not mean `trust-model.md` stops mentioning what deep-path context looks like.
2. **Down-layer facts should not creep up.** If the README first screen starts explaining retry strategies, the layering is broken — move it to `architecture.md` and link.
3. **Every claim on the first screen must be reachable from a file-level anchor** in this repo. If it is not, either remove the claim or go add the implementation that backs it.
4. **v2 is visible, not front-loaded.** The first screen names v2 once (paths overview), describes why deeper paths exist, and stops. v2 internals live in `docs/architecture.md`.
5. **Release notes do not redefine the product.** If a release note needs to say "Cold Eyes is now a full-context reviewer" — either the positioning has been formally changed (update `positioning_audit.md` and the README first, then release), or the sentence is wrong.

---

## When this matrix needs updating

- A new doc is added that takes on a new audience (e.g. `docs/for-maintainers.md`).
- The GitHub About / topics are changed — record the new wording here.
- A new major feature lands (a new gate, a new review path). Add it as a row; decide every column.
- `positioning_audit.md` is rewritten with a new target positioning sentence.

Owner: whoever edits the README first screen or the GitHub About. They are the layer-1 gatekeepers.
