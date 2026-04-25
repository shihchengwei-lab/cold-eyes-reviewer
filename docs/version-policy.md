# Version Policy

Cold Eyes Reviewer follows [Semantic Versioning 2.0.0](https://semver.org/).

## Version bumps

| Bump | When |
|------|------|
| **MAJOR** (X.0.0) | Breaking changes to: CLI interface, hook JSON output format, history schema / gate schema semantics, gate decision behavior, or environment variable semantics |
| **MINOR** (0.X.0) | New features: CLI commands, environment variables, policy keys, history fields, eval modes |
| **PATCH** (0.0.X) | Bug fixes, documentation improvements, test additions, CI changes |

## Version signals

Four places must agree on every release:

1. `cold_eyes/__init__.py` (`__version__`)
2. `CHANGELOG.md` (top entry)
3. Git tag (`vX.Y.Z`)
4. GitHub Release title

The release workflow (`.github/workflows/release.yml`) enforces tag-to-`__version__` alignment automatically. See `docs/release-checklist.md` for the full pre-release procedure.

## History schema versioning

The model review `schema_version` field is versioned independently from the package version. It only increments on breaking changes to the LLM review JSON structure. Current model review schema version: 1.

The v2 gate envelope has its own `GATE_SCHEMA_VERSION` because gate state, cache identity, and no-silent-pass decisions are outside the LLM review issue schema. Current gate envelope schema version: 2.
