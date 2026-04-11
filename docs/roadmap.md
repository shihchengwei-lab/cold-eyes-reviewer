# Roadmap

This is a personal tool. The roadmap is directional, not committed.

## Current priorities (v1.3.x)

- Governance documentation (CONTRIBUTING, SECURITY, templates)
- CI coverage gate and release workflow
- Troubleshooting guide and failure mode documentation

## Possible future work

- Expand eval cases based on real-world usage patterns
- Measure `line_hint` hallucination rate via eval framework
- Custom review prompt validation (syntax check before deploy)
- Per-project override policy configuration
- Coverage gate in CI (`pytest --cov` threshold enforcement)

## Explicitly out of scope

- GUI or web dashboard
- Daemon or long-running background service
- PyPI or package registry distribution
- Multi-user or team features
- Commercial licensing or paid tiers
- Fancier prompts (the current ceiling is not the prompt)
