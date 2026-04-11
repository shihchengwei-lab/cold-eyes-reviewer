# Support Policy

## Runtime requirements

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| Python | 3.10+ | No third-party dependencies at runtime |
| Git | 2.x+ | Used via subprocess for diff collection |
| Shell | Bash | Git Bash on Windows; zsh/fish untested but may work |
| Claude Code | Latest | CLI invoked via subprocess; no minimum version pinned |

## Tested platforms

CI runs on every push and pull request:

| OS | Python 3.10 | Python 3.12 |
|----|-------------|-------------|
| Ubuntu (latest) | Tested | Tested |
| macOS (latest) | Tested | Tested |
| Windows (latest) | Tested | Tested |

Additionally: `ruff` lint and `shellcheck` run on Ubuntu/Python 3.12.

## Windows notes

- Use Git Bash, not PowerShell or CMD
- The `mkdir`-based lock and `kill -0` stale PID check work in Git Bash but are less reliable than on native Unix
- Subprocess encoding is forced to UTF-8 (fixed in v1.2.0)

## Maintenance model

This is a personal project maintained on a best-effort basis. File issues on [GitHub](https://github.com/shihchengwei-lab/cold-eyes-reviewer/issues).
