"""Risk classifier — session-level risk aggregation from file metadata."""

from cold_eyes.constants import RISK_CATEGORIES
from cold_eyes.triage import classify_file_role

RISK_LEVELS = ("low", "medium", "high", "critical")


def classify_risk(
    changed_files: list[str],
    contracts: list[dict] | None = None,
) -> dict:
    """Classify the overall risk level of a set of changed files.

    Returns dict with:
        risk_level       ("low" | "medium" | "high" | "critical")
        risk_factors     (list[str] — human-readable reasons)
        risk_categories  (list[str] — matched RISK_CATEGORIES keys)
        recommended_depth ("skip" | "shallow" | "deep")
    """
    contracts = contracts or []
    factors: list[str] = []
    matched_cats: set[str] = set()

    if not changed_files:
        return {
            "risk_level": "low",
            "risk_factors": ["no files changed"],
            "risk_categories": [],
            "recommended_depth": "skip",
        }

    roles = {f: classify_file_role(f) for f in changed_files}

    # --- File role signals ---
    source_count = sum(1 for r in roles.values() if r == "source")
    migration_count = sum(1 for r in roles.values() if r == "migration")
    docs_count = sum(1 for r in roles.values() if r in ("docs", "config", "generated"))

    if migration_count:
        factors.append(f"{migration_count} migration file(s)")
    if source_count > 5:
        factors.append(f"large change: {source_count} source files")

    # --- Risk category matching ---
    combined_paths = " ".join(changed_files)
    for cat_name, pattern in RISK_CATEGORIES.items():
        if pattern.search(combined_paths):
            matched_cats.add(cat_name)
            factors.append(f"risk category: {cat_name}")

    # --- Contract risk categories ---
    for c in contracts:
        for rc in c.get("risk_categories", []):
            if rc not in matched_cats:
                matched_cats.add(rc)
                factors.append(f"contract risk: {rc}")

    # --- Determine level ---
    score = 0
    score += len(matched_cats) * 2
    score += migration_count * 3
    score += max(0, source_count - 3)  # large changes
    # Must-priority contracts add weight
    score += sum(1 for c in contracts if c.get("priority") == "must")

    if score == 0 and docs_count == len(changed_files):
        level = "low"
        depth = "skip"
    elif score <= 2:
        level = "low"
        depth = "shallow"
    elif score <= 5:
        level = "medium"
        depth = "deep"
    elif score <= 10:
        level = "high"
        depth = "deep"
    else:
        level = "critical"
        depth = "deep"

    if not factors:
        factors.append("no specific risk signals detected")

    return {
        "risk_level": level,
        "risk_factors": factors,
        "risk_categories": sorted(matched_cats),
        "recommended_depth": depth,
    }
