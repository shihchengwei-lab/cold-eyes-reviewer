# Version Policy

Cold Eyes Reviewer follows [Semantic Versioning 2.0.0](https://semver.org/).

## Version bumps

| Bump | When |
|------|------|
| **MAJOR** (X.0.0) | Breaking changes to: CLI interface, hook JSON output format, history schema (`schema_version`), or environment variable semantics |
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

The `schema_version` field in review output is versioned independently from the package version. It only increments on breaking changes to the review JSON structure. Current schema version: 1.
