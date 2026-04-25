# Disclosure Matrix

Where each fact about Cold Eyes belongs. Use this to decide what goes on the homepage, what belongs deeper, and what should never appear on a release note.

## Layer Rules

| Layer | Audience goal | Should disclose | Should not front-load |
|---|---|---|---|
| GitHub About | Identify the project in one glance | Claude Code, second-pass gate, diff-centered, Stop hook | retry history, internal modules, token budgets |
| README first screen | Decide whether to try it | what it is, what it is not, best-fit, poor-fit, shallow/deep/local-check overview | full architecture, override internals, exhaustive config |
| README advanced sections | Operate and tune it | configuration keys, failure modes, diagnostics, history, known limitations | internal implementation rationale |
| `docs/` advanced | Maintain and audit it | architecture, local-check behavior, override lifecycle, calibration rules, eval corpus, assurance matrix | none; this is the catch-all |
| Release notes | Understand what changed | behavior, cost, context, blocking-policy, migration, affected audience | product redefinition or mini-README prose |

## Fact Mapping

| Fact / feature | GitHub About | README first screen | README advanced | docs advanced | Release notes |
|---|---|---|---|---|---|
| Diff-centered second-pass gate | yes | yes | yes | trust model | only if positioning changes |
| Not full review / not strong intent system | yes | yes | yes | assurance matrix | only if changed |
| Shallow / deep paths | hint | yes | how-it-works | architecture | when behavior changes |
| Automatic local checks | hint | yes | configuration + limitations | architecture | when checks/defaults change |
| No-silent-pass delta gate | hint | yes | scope + failure modes | architecture + trust model | when gate state/policy changes |
| Bounded context | no | yes | how-it-works | trust model | when context changes |
| Detector hints | no | no | how-it-works | architecture | when logic changes |
| Override token | no | no | configuration | trust model | when TTL/scope changes |
| Token budgets and cost | no | yes | configuration | tuning | when defaults change |
| Policy keys | no | no | configuration | config docs | when keys add/remove |

## Rules of Thumb

1. Up-layer facts do not replace detailed docs.
2. Down-layer internals should not creep into the first screen.
3. Every first-screen claim should map to an implementation or doc anchor.
4. Local checks and the v2 envelope are visible as unified protection layers, not separate product modes.
5. Release notes do not redefine what Cold Eyes is.
