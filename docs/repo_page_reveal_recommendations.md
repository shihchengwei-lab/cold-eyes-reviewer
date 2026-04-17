# Repo Page Reveal Recommendations

Ready-to-paste copy for the GitHub repo surfaces that are not files in this repo: the About box, topics list, pinned snippets, release pages.

All drafts are aligned to the target positioning in `docs/positioning_audit.md` §6 and the layer rules in `docs/disclosure_matrix.md`.

---

## 1. GitHub About — description

### 1.1 Short form (≤ 160 chars, fits GitHub mobile + rendered badges)

> Diff-centered second-pass review gate for Claude Code. Runs as a Stop hook. Deep paths add bounded context. Not a full code review.

Character count: ~137.

### 1.2 Medium form (≤ 240 chars, GitHub About default width)

> Diff-centered second-pass review gate for Claude Code. Runs as a Stop hook after each session turn. Deep paths add limited structured context (recent commits, co-changed files) + detector hints. Not a full code review; not intent-aware.

Character count: ~239.

### 1.3 Current About (for reference, replace this)

> Cold-read code review engine for Claude Code Stop hooks (or equivalent previous text)

---

## 2. GitHub topics

Apply the set below. Order matters only lightly — the first three are the primary identifiers.

### Recommended topics

- `claude-code`
- `review-gate`
- `git-hooks`
- `code-quality`
- `llm-guardrails`
- `developer-tools`
- `second-pass-review`

### Avoid as primary

- `ai-code-review` — too broad; attracts audiences expecting a full PR platform. If you keep it at all, keep it as a secondary topic, not a primary one.
- `platform` — implies surface area we do not claim.
- `governance` — same.
- `code-review` (unqualified) — implies a PR-review product.

---

## 3. Pinned / top-of-README snippets

GitHub renders the first ~200 characters of README prominently. The current first-screen work already lives in `README.md`; the items below are for surfaces around the README.

### 3.1 Test badge (already present)

Keep the existing test badge.

### 3.2 Optional positioning badges

If the project adopts shields.io style badges, the following plain-text badges are aligned and low-noise:

- `Stop-hook for Claude Code`
- `Diff-centered + bounded context`
- `Not a full code review`

Do not add a badge for v2, retry count, gate count, or suppression — those are implementation details and will drift.

### 3.3 Social preview image

If the repo has a social preview (`Settings → Social preview`), keep it textual and narrow. Suggested text:

> Cold Eyes
> A diff-centered second-pass gate for Claude Code.
> Second pair of eyes, runs on Stop.

Do not put feature bullet lists on the social preview.

---

## 4. Release / tag pages — fixed disclosure checklist

Every release description (the body that appears on the GitHub `Releases` page for a tag) must answer each of these, even briefly. The full template lives in `docs/release_note_template.md`; the points below are the minimum that must appear on the GitHub release UI itself.

1. **What changed** — 1–2 sentences, imperative voice.
2. **Behavior changes** — what a Stop-hook invocation does differently. `none` is a valid answer.
3. **Cost changes** — token budget defaults, per-run worst case if v2-related. `none` is valid.
4. **Context usage changes** — whether the deep path pulls more, less, or different context. `none` is valid.
5. **Blocking policy changes** — changes to `block_threshold`, `confidence`, `truncation_policy`, or similar defaults. `none` is valid.
6. **Migration / opt-in notes** — is this a bare version bump, is `--v2` required, is an env var renamed?
7. **Who should care** — the audience line. Example: `Stop-hook users on block mode.` or `v2 adopters only.`

If all six lines are `none`, the release body should still include the checklist with `none` values, so a reader can tell at a glance that nothing about the product's behaviour shifted.

### Do not

- Do not use the release body to redefine the product ("Cold Eyes is a comprehensive...").
- Do not front-load retry internals, gate internals, or assurance matrix content.
- Do not use the release body as a mini-README.

---

## 5. Where these recommendations live

- **This file** (`docs/repo_page_reveal_recommendations.md`) — the source of truth for the About text, topics list, badge phrasing, and release disclosure checklist.
- **`docs/disclosure_matrix.md`** — the "what goes where" rules that make these recommendations consistent with in-repo docs.
- **`docs/release_note_template.md`** — the per-release full template.

When any of these is updated, cross-check the other two.

---

## 6. Application checklist (when you apply these to GitHub UI)

- [x] Paste §1.2 into the About description field. *(applied 2026-04-17 via `gh repo edit`)*
- [x] Clear current topics; apply §2 list. *(applied 2026-04-17: claude-code, review-gate, git-hooks, code-quality, llm-guardrails, developer-tools, second-pass-review)*
- [x] Review pinned README snippet area; add §3.2 positioning badges. *(applied 2026-04-17: Stop-hook / diff-centered / not full review, alongside existing Tests badge)*
- [x] On the next `Releases` entry, paste the §4 checklist. *(applied 2026-04-17: v1.11.4 release)*
