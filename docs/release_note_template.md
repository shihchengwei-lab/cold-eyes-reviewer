# Release Note Template

Use this structure for every release. Goal: a reader can tell in under a minute whether this release changes anything about the product's behaviour, cost, or blocking posture.

The template is aligned to the layer rules in `docs/disclosure_matrix.md` (release notes are a separate disclosure layer and must not redefine the product) and to the GitHub release disclosure checklist in `docs/repo_page_reveal_recommendations.md` §4.

---

## Copy this block into `CHANGELOG.md` under a new `## vX.Y.Z — <short title>` heading

```markdown
## vX.Y.Z — <short title: one phrase, e.g. "v2 default mode", "retry cap tightening", "docs-only pass">

### What changed

<1–2 sentences. Imperative voice. "Add X", "Change Y to Z", "Fix N".>

### Behavior changes

- `none` *or*
- What a Stop-hook run does differently. One bullet per user-visible behavior delta.
  - Include the env var / flag / config key that is affected.

### Cost changes

- `none` *or*
- Token budget default changes, worst-case per-run shifts (especially v2 retries), model-default changes.
  - If v2 retry cap changes, state the new worst case multiplier explicitly.

### Context usage changes

- `none` *or*
- Deep-path context block size changes, detector-hint additions/removals, new inputs to the LLM review step.
  - If the deep path starts reading new files or git ranges, say so.

### Blocking / policy changes

- `none` *or*
- Default `block_threshold`, `confidence`, `truncation_policy` changes, new `critical_checks` in `doctor`, state machine transitions that can now emit `blocked`.

### Migration / opt-in notes

- `none` *or*
- Is `--v2` required to see the new behavior? Is an env var renamed or deprecated? Is a config key moved?
- If a user does nothing, what do they see?

### Who should care

<One line. Examples: "All Stop-hook users." / "v2 adopters only." / "Users on block mode with custom thresholds." / "Docs-only — no one who isn't reading docs.">

### Details

<Full technical detail goes here. Bullet per change, grouped by Major / Minor / Production / Tests / Docs as the repo has done historically.>
```

---

## Rules

### Every section is mandatory

Even if the answer is `none`, the heading must appear. A release with `none` in every section should still render all six checklist headings — that is the signal "this release changes nothing user-visible". Do not shorten.

### Do not redefine the product

Release notes are not a place to reintroduce the positioning statement. If you feel the need to write "Cold Eyes is a ...", stop. That sentence belongs in `README.md` and the GitHub About. If the release genuinely changes the positioning (a narrow-positioning pass, a rename, a scope change), update `docs/positioning_audit.md` first, land the README rewrite, then do the release. The release body can then link to the audit and to the new README section — no re-framing in prose.

### Include env / flag / config names

Every behavior change bullet should mention the actual identifier a user can grep for: `COLD_REVIEW_MODE`, `block_threshold`, `--v2`, `arm-override`, etc. This keeps release notes searchable and avoids vague wording.

### Audience line is hard to fake

The "Who should care" line forces the writer to state who is affected. If the honest answer is "nobody who doesn't read docs", say that. It keeps `docs-only` releases from looking like behavior changes.

---

## Worked example — docs-only release

```markdown
## v1.11.4 — docs: narrow-positioning pass

### What changed

Narrow the outward-facing positioning to "diff-centered second-pass gate for Claude Code" across pyproject, package docstring, prompt fallback, README, trust-model, and assurance-matrix. Add disclosure matrix, repo page reveal recommendations, release note template, and a positioning audit + consistency checklist.

### Behavior changes

- `none`

### Cost changes

- `none`

### Context usage changes

- `none` (deep path still loads the same recent commits + co-changed files; detector hints unchanged)

### Blocking / policy changes

- `none`

### Migration / opt-in notes

- `none`. `import cold_eyes` module docstring text and `pyproject` description change are metadata-only.

### Who should care

Readers of the README or the GitHub About. No runtime behavior change.

### Details

- …
```

---

## Worked example — behavior change

```markdown
## vX.Y.Z — tighten v2 retry abort threshold

### What changed

Lower the v2 retry abort threshold from 3 retries to 2 retries.

### Behavior changes

- `--v2` sessions now abort after 2 retries instead of 3 (file: `cold_eyes/retry/strategy.py`). Total runs per session: initial + 2 retries = 3 (was 4).

### Cost changes

- Worst-case token cost for `--v2` sessions drops from 4x v1 to 3x v1.

### Context usage changes

- `none`

### Blocking / policy changes

- `failed_terminal` now reached sooner on non-converging sessions. `passed` outcome unaffected.

### Migration / opt-in notes

- v2 adopters who relied on the 4-run worst case should confirm their retry-sensitive logic.

### Who should care

`--v2` adopters only. v1 users unaffected.

### Details

- …
```
