# Roadmap

This is a personal tool. The roadmap is directional, not committed.

## Trust engineering roadmap

Based on external review, the project follows a phased trust engineering plan. The goal: make Cold Eyes externally auditable, not just internally tested.

### Phase 1 — Verifiable trust baseline (complete)

- [x] Expand eval corpus to 24 cases across 5 categories
- [x] Add manifest.json and schema.md for eval case format
- [x] Add validate_manifest() for CI-level corpus consistency
- [x] Create trust-model.md (what it can/cannot detect, trust properties)
- [x] Expand SECURITY.md trust boundaries (attack surface table, input/output handling)
- [x] Create assurance-matrix.md (per-category detectability, FP/FN direction)
- [x] Structured eval pipeline output (markdown summary, save, compare)
- [x] CLI flags for eval (--save, --format, --compare)
- [x] Regression gate + baseline management
- [x] CI eval integration (deterministic + regression check)

### Cost-effective triage (v1.5.0)

- [x] 8 risk categories (auth, state, migration, persistence, API, async, secrets, cache)
- [x] 6 file roles (test, docs, config, generated, migration, source)
- [x] Skip / shallow / deep three-tier triage in engine pipeline
- [x] Skip path: zero model calls for docs/generated/config-only changes

### Shallow differentiation + context retrieval (v1.6.0)

- [x] Shallow prompt (critical-only, shorter template)
- [x] Lighter model for shallow reviews (configurable, default sonnet)
- [x] Context retrieval from git history for deep reviews
- [x] Triage distribution in quality report

### Evidence-bound claim schema (v1.7.0)

- [x] Evidence chain fields on issues (evidence, what_would_falsify_this, suggested_validation)
- [x] Abstain condition field + confidence downgrade
- [x] calibrate_evidence() in policy pipeline (before confidence filter)
- [x] Deep prompt updated to require evidence chains
- [x] 3 evidence-bound eval cases (27 total)
- [x] Bugfixes: triage regex, CJK token estimation, README env vars, shell guard

### State/invariant + repo-specific detectors (v1.8.0)

- [x] State/invariant detector: 5 signal patterns (state_check, transition_call, fsm, rollback, assignment)
- [x] Repo-type classifier (web_backend, sdk_library, db_data, infra_async, general)
- [x] 4 focus profiles with targeted checks per repo type
- [x] Detector hints injected into deep review path before model call
- [x] Engine outcome fields: detector_repo_type, detector_focus, state_signal_count
- [x] 3 state/invariant eval cases (30 total)

### False-positive memory + confidence calibration (v1.9.0)

- [x] FP pattern extraction from override history (category, path, check prefix)
- [x] FP pattern matching integrated into calibrate_evidence() (Rule 3: -1 per match type, max -2)
- [x] Per-category confidence caps (Rule 4: high-ratio categories capped at medium/low)
- [x] Engine wiring: extract_fp_patterns() runs before apply_policy()
- [x] 3 FP memory eval cases (33 total)

### Phase 2 — External evidence (future)

- Release-by-release assurance notes (`docs/reports/vX.Y.Z-assurance.md`)
- Challenge set (adversarial cases, separate from main benchmark)
- Incident / miss postmortem template and initial entries
- Head-to-head comparison framework (dimensions, not necessarily competitors)

### Phase 3 — Governance and adoption (future)

- Adoption profiles (solo conservative, team guardrail, high-trust strict)
- Architecture Decision Records (ADRs) for key design choices
- Trust-facing release discipline (behavior/risk/eval diff per release)

### Phase 4 — Continuous trust operations (future)

- Trust report automation (benchmark + challenge + override + history → report)
- Data feedback loop (override reasons → benchmark corpus → policy defaults)
- Trust KPIs (override rate, FP rate, infra-fail rate, truncation rate)
- Homepage rewrite (assurance-first, not feature-first)

## Explicitly out of scope

- GUI or web dashboard
- Daemon or long-running background service
- PyPI or package registry distribution
- Multi-user or team features
- Commercial licensing or paid tiers
- Fancier prompts (the current ceiling is not the prompt)
- More provider abstractions or integrations
