# Positioning Consistency Checklist

Use this as a drift guard whenever README, About text, prompts, or release notes change.

## Current Target

Cold Eyes is a diff-centered, second-pass gate for Claude Code. It treats staged changes as primary intent, scans source/config working-tree delta so it cannot silently pass, may use bounded supporting context on deeper paths, and selected local checks run in the same unified v2 flow. It is not a full code review system and does not claim strong requirement or intent understanding.

## Checklist

- [ ] README first screen says diff-centered, not diff-only.
- [ ] README names local checks and envelope scanning as part of unified v2, not as separate modes.
- [ ] README explains that local checks run once and do not create repair memory.
- [ ] GitHub About stays short: Claude Code, second-pass gate, Stop hook, diff-centered.
- [ ] Release notes mention concrete identifiers such as `COLD_REVIEW_CHECKS` when behavior changes.
- [ ] Docs do not reintroduce the retired session/retry path as a current product mode or active source package.
- [ ] `rg -i "zero-context|diff-only|only reads the diff"` has no new non-historical hits.

## Intentionally Historical

Old changelog entries may preserve earlier wording. Do not rewrite release history solely for positioning cleanup.
