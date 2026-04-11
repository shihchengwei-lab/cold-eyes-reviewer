# Contributing to Cold Eyes Reviewer

Thank you for your interest in contributing. This document covers development setup, coding standards, and contribution workflow.

## Development setup

```bash
git clone https://github.com/shihchengwei-lab/cold-eyes-reviewer.git
cd cold-eyes-reviewer
pytest tests/ -v          # run all tests
ruff check cold_eyes/ tests/  # lint
```

No additional Python dependencies are required beyond the standard library. `pytest` and `ruff` are dev-only tools.

## Code style

- Linter: [Ruff](https://docs.astral.sh/ruff/), configured in `pyproject.toml`
- Line length: 130 characters
- Rules: E (pycodestyle errors), F (pyflakes), W (pycodestyle warnings)
- No type annotations required (not currently used in the codebase)

Run `ruff check cold_eyes/ tests/` before submitting. CI enforces this.

## Testing

- All changes must pass the full test suite
- Add tests to existing test files in `tests/` rather than creating new ones
- Use fixtures from `tests/conftest.py` (`fixture_path`, `scripts_dir`, `shell_script`)
- Test fixtures go in `tests/fixtures/`
- Eval cases go in `evals/cases/`

## Commit convention

Follow the existing pattern:

```
type(scope): description
```

Common types: `fix`, `feat`, `docs`, `ci`, `refactor`, `test`

Examples from the repo:
- `fix(windows): force UTF-8 encoding in git_cmd subprocess`
- `docs: update README for v1.2.0`
- `v1.3.0: governance, CI coverage, actionable diagnostics`

## Pull requests

- One logical change per PR
- CI must be green (tests + lint + shellcheck)
- Reference the related issue number if applicable
- For version bumps: ensure all four version signals are aligned (`__init__.py`, CHANGELOG, git tag, GitHub Release)

## Deployment model

Cold Eyes deploys via `cp -r` to `~/.claude/scripts/`, not via `pip install`. This is intentional -- the Stop hook must be self-contained and not depend on a specific Python environment.

**Do not add Python dependencies.** The package uses only the standard library. `pytest`, `pytest-cov`, and `ruff` are dev-only and not required at runtime.

## Scope

This is a personal tool. Feature requests are welcome, but the project explicitly does not aim for:
- GUI or dashboard
- Daemon or long-running service
- PyPI distribution
- Multi-user or team features

See `docs/roadmap.md` for current priorities and out-of-scope items.
