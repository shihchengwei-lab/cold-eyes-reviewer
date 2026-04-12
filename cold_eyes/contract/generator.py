"""Contract generator — rule-based contract generation from file metadata."""

from cold_eyes.constants import RISK_CATEGORIES
from cold_eyes.contract.schema import create_contract
from cold_eyes.triage import classify_file_role


def generate_contracts(
    task_description: str,
    changed_files: list[str],
    risk_types: list[str] | None = None,
) -> list[dict]:
    """Generate correctness contracts from task metadata.

    Pure rule-based, deterministic.  Uses file roles and risk categories
    to decide which contracts are needed.
    """
    if not changed_files:
        return []

    contracts: list[dict] = []
    roles = {f: classify_file_role(f) for f in changed_files}
    risk_types = risk_types or []

    source_files = [f for f, r in roles.items() if r == "source"]
    test_files = [f for f, r in roles.items() if r == "test"]
    migration_files = [f for f, r in roles.items() if r == "migration"]

    # 1. If there are test files -> test_pass contract
    if test_files:
        contracts.append(create_contract(
            intended_change=task_description,
            check_type="test_pass",
            priority="must",
            target_files=test_files,
            problem_being_solved="existing tests must still pass",
        ))

    # 2. If there are source files -> lint_clean contract
    if source_files:
        contracts.append(create_contract(
            intended_change=task_description,
            check_type="lint_clean",
            priority="should",
            target_files=source_files,
            problem_being_solved="source files must be lint-clean",
        ))

    # 3. If risk categories are hit -> llm_review contract
    matched_risks = _match_risks(changed_files, risk_types)
    if matched_risks or source_files:
        contracts.append(create_contract(
            intended_change=task_description,
            check_type="llm_review",
            priority="must" if matched_risks else "should",
            target_files=source_files or changed_files,
            risk_categories=matched_risks,
            problem_being_solved="deep review for risky surfaces",
        ))

    # 4. Migration files -> dedicated contract
    if migration_files:
        contracts.append(create_contract(
            intended_change=task_description,
            check_type="custom",
            priority="must",
            target_files=migration_files,
            risk_categories=["migration_schema"],
            problem_being_solved="migration must be reversible and schema-safe",
            likely_failure_modes=["irreversible schema change", "data loss"],
        ))

    return contracts


def _match_risks(files: list[str], explicit_risks: list[str]) -> list[str]:
    """Return risk category names matched by file paths or explicit list."""
    matched: set[str] = set(explicit_risks)
    combined = " ".join(files)
    for cat_name, pattern in RISK_CATEGORIES.items():
        if pattern.search(combined):
            matched.add(cat_name)
    return sorted(matched)
