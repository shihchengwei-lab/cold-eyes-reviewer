# Positioning Consistency Checklist

Tracker for the narrow-positioning documentation pass. Each row is one concrete rewrite. Use this as a PR checklist and a future drift guard.

**Target positioning:** Cold Eyes is a diff-centered, second-pass gate for Claude Code. Deep paths use limited, structured supporting context. Not a full code review; not intent-aware.

Status legend: `[ ]` pending, `[x]` done, `[-]` intentionally skipped.

---

## Commit 2 — Core string alignment + README restructure

### C2.1 `pyproject.toml:8` — project description
- [ ] Current: `description = "Zero-context code review engine for Claude Code Stop hooks"`
- [ ] Replace with: `description = "Diff-centered second-pass review gate for Claude Code"`
- **Problem type:** absolute "Zero-context" phrase; appears on PyPI, `pip show`, and GitHub package metadata.
- **Rationale:** deep path loads bounded context via `cold_eyes/context.py:32`; current wording contradicts implementation.

### C2.2 `cold_eyes/__init__.py:1` — package docstring
- [ ] Current: `"""Cold Eyes Reviewer — zero-context code review engine."""`
- [ ] Replace with: `"""Cold Eyes Reviewer — diff-centered second-pass review gate for Claude Code."""`
- **Problem type:** same as C2.1; propagates to `help(cold_eyes)` and any tooling that reads the module docstring.
- **Rationale:** match pyproject description.

### C2.3 `cold_eyes/prompt.py:42` — fallback prompt string
- [ ] Current: `"You are Cold Eyes, a zero-context reviewer. Review the diff. Output JSON: {pass, issues, summary}."`
- [ ] Replace with: `"You are Cold Eyes, a diff-centered reviewer. Review the diff. Output JSON: {pass, issues, summary}."`
- **Problem type:** fallback prompt used only when template file missing, but still shapes model disposition.
- **Rationale:** "Cold Eyes" name has semantic function for LLM disposition; prompt wording matters.

### C2.4 `tests/test_shallow_and_context.py:31` — deep prompt assertion
- [ ] Current: `assert "邏輯錯誤" in text or "zero-context" in text.lower()`
- [ ] Replace with: `assert "邏輯錯誤" in text or "diff-centered" in text.lower()`
- **Problem type:** OR-fallback anchors a phrase we are removing.
- **Rationale:** keep the CJK primary clause; update fallback to match new prompt wording.

### C2.5 `README.md` — L5 tagline + L9 positioning paragraph
- [ ] Current L5: `A cold-read code reviewer for [Claude Code]...`
- [ ] Current L9: `Cold Eyes is a second-pass gate, not a full code review. It has no conversation context and no requirements. Deep reviews see the git diff plus limited structured context ... and regex-based detector hints. Shallow reviews see only the diff. ...`
- [ ] Replace L5 with one-sentence positioning aligned to target.
- [ ] Replace L9 paragraph with "What it is" block.
- **Problem type:** absolute wording ("no context", "only the diff") and missing what-it-isn't framing.
- **Rationale:** roadmap §1.3.

### C2.6 `README.md` — add `What it is not`, `When it works best`, `When not to use it as a blocking gate` sections
- [ ] Insert after the positioning paragraph, before `How it works`.
- [ ] `What it is not` — 5 bullets (roadmap §2.1).
- [ ] `When it works best` — 3-4 bullets (best-fit).
- [ ] `When not to use it as a blocking gate` — 4+ bullets (roadmap §2.2 + poor-fit).
- **Rationale:** roadmap §2; current README has no such sections.

### C2.7 `README.md` — add `Review paths overview` section
- [ ] Short summary of shallow / deep / v2 paths (2-3 sentences each).
- [ ] Place after `Recommended adoption path`, before the technical `How it works` block.
- **Rationale:** v2 must stay visible without dominating (roadmap §5).

---

## Commit 3 — Disclosure scaffolding

### C3.1 `docs/disclosure_matrix.md`
- [ ] New file. Roadmap §3 table: 5 layers (GitHub About / README first screen / README advanced / docs advanced / release notes) × (what to reveal / what not to front-load).

### C3.2 `docs/repo_page_reveal_recommendations.md`
- [ ] New file. Roadmap §4: GitHub About drafts (160 char + 240 char), topics list, pinned badges/snippets, release/tag page disclosure checklist.

### C3.3 `docs/release_note_template.md`
- [ ] New file. Roadmap §6 seven-section structure: What changed / Behavior / Cost / Context usage / Blocking policy / Migration / Audience.

---

## Commit 4 — Residual cleanup + version bump

### C4.1 `docs/trust-model.md:7` — "What Cold Eyes is" paragraph
- [ ] Current: `"A zero-context second-pass gate. It reads a git diff and produces a block/pass verdict. It sees only the diff — no conversation, no project history, no requirements, no full codebase."`
- [ ] Replace with a paragraph that says: diff-centered; deep path uses bounded structured context (recent commits, co-changed files) + detector hints; no conversation / no requirements / no full codebase access.
- **Problem type:** absolute "zero-context" + "only the diff".
- **Rationale:** contradicts `cold_eyes/context.py`.

### C4.2 `docs/trust-model.md:9` — keep as is
- [x] `"It is not an AI code reviewer in the general sense. It is a risk gate that catches surface-level issues visible in a single diff."`
- **Rationale:** this is a correct narrow-positioning sentence; intentionally retained.

### C4.3 `docs/assurance-matrix.md:14` — consistency category row
- [ ] Current: `"Inherently limited by zero-context design"`
- [ ] Replace with: `"Inherently limited — cross-document inconsistency requires full-context view Cold Eyes does not have"`

### C4.4 `docs/assurance-matrix.md:49` — "Scope limitations" header line
- [ ] Current: `"What zero-context review cannot do, and workarounds where they exist."`
- [ ] Replace with: `"What a diff-centered review cannot do, and workarounds where they exist."`

### C4.5 `cold_eyes/__init__.py` — version bump
- [ ] `__version__ = "1.11.3"` → `__version__ = "1.11.4"`

### C4.6 `CHANGELOG.md` — add v1.11.4 entry
- [ ] Heading: `## v1.11.4 — docs: narrow-positioning pass`
- [ ] Summary: outward-facing copy aligned to "diff-centered second-pass gate"; no behavior changes, no new gates, no cost impact.
- [ ] List: pyproject / `__init__` / prompt fallback / test assertion / README rewrite / new docs (audit, checklist, disclosure matrix, repo page recommendations, release note template) / trust-model + assurance-matrix cleanup.

### C4.7 `HANDOVER.md` — update version signals section
- [ ] `__init__.py = 1.11.3` → `1.11.4`
- [ ] CHANGELOG = v1.11.4
- [ ] pytest = 774 passed (unchanged)
- [ ] Note Session 7 entry under "本次會話做了什麼".

---

## CHANGELOG history — intentionally not rewritten

- `[-]` `CHANGELOG.md:183` — `"shallow reviews as diff-only."` — historical record of the v1.9.0 terminology shift. Changelogs are immutable history; do not rewrite.

---

## Verification gates

Run after each commit, all must pass:

1. `pytest` → 774 passed, 0 failed.
2. `rg -i "zero-context|diff-only|only reads the diff|only the diff"` across repo, excluding `CHANGELOG.md` and `docs/positioning_audit.md` → zero hits.
3. `python -c "import cold_eyes; print(cold_eyes.__version__)"` → matches current commit's target version.
4. Read README top 500 words — can answer: what is it / what isn't it / when to use / when not to?

---

## Future drift guard

Any PR that touches the following files must cross-check this checklist:

- `README.md` (top 50 lines)
- `pyproject.toml` (`description`)
- `cold_eyes/__init__.py` (docstring, `__version__`)
- `cold_eyes/prompt.py` (fallback strings)
- `cold-review-prompt.txt` / `cold-review-prompt-shallow.txt` (template files)
- `docs/trust-model.md`
- `docs/assurance-matrix.md`

If new positioning sentences appear, they must be traceable back to the target positioning in `docs/positioning_audit.md` §6.
