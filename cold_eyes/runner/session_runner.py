"""End-to-end session runner — v2 top-level entry point.

Orchestrates: session → contracts → risk → gates → noise → retry loop → outcome.
"""

from cold_eyes.contract.generator import generate_contracts
from cold_eyes.contract.quality_checker import check_quality
from cold_eyes.gates.catalog import available_gates
from cold_eyes.gates.orchestrator import run_gates
from cold_eyes.gates.risk_classifier import classify_risk
from cold_eyes.gates.selection import build_gate_plan
from cold_eyes.noise.calibration import calibrate
from cold_eyes.noise.dedup import merge_duplicates
from cold_eyes.noise.retry_suppression import suppress_seen
from cold_eyes.retry.stop import should_stop
from cold_eyes.retry.strategy import select_strategy
from cold_eyes.retry.translator import translate
from cold_eyes.session.schema import add_event, create_session
from cold_eyes.session.state_machine import transition


def run_session(
    task_description: str,
    changed_files: list[str],
    *,
    max_retries: int = 3,
    engine_adapter=None,
    engine_kwargs: dict | None = None,
    gate_timeout: int = 120,
    available_gate_ids: list[str] | None = None,
) -> dict:
    """Run the full v2 correctness session.

    Parameters
    ----------
    task_description : str
        What the change is about.
    changed_files : list[str]
        Files modified in this change.
    max_retries : int
        Maximum retry iterations (default 3).
    engine_adapter : optional
        Model adapter for the llm_review gate (MockAdapter for tests).
    engine_kwargs : dict, optional
        Extra kwargs for engine.run() in the llm_review gate.
    gate_timeout : int
        Timeout in seconds for external gate subprocesses.
    available_gate_ids : list[str], optional
        Override for available gates (defaults to auto-detection).

    Returns
    -------
    dict — SessionRecord with final_outcome populated.
    """
    session = create_session(task_description, changed_files)

    # --- Phase A: Contracts ---
    contracts = generate_contracts(task_description, changed_files)
    session["contracts"] = contracts
    transition(session, "contract_generated")
    add_event(session, "contracts_generated", {"count": len(contracts)})

    quality = check_quality(contracts, changed_files)
    add_event(session, "quality_checked", quality)

    # --- Phase B: Gate planning ---
    risk = classify_risk(changed_files, contracts)
    add_event(session, "risk_classified", risk)

    if available_gate_ids is None:
        available_gate_ids = available_gates()
    gate_plan = build_gate_plan(risk["risk_level"], contracts, available_gate_ids)
    session["gate_plan"] = [g["gate_id"] for g in gate_plan["selected_gates"]]
    transition(session, "gates_planned")
    add_event(session, "gate_plan_built", {
        "selected": len(gate_plan["selected_gates"]),
        "skipped": len(gate_plan["skipped_gates"]),
    })

    # --- Phase B+C: Gate execution + retry loop ---
    all_previous_findings: list[dict] = []
    previous_briefs: list[dict] = []
    gates_to_run = gate_plan["selected_gates"]

    for iteration in range(max_retries + 1):
        transition(session, "gates_running")

        results = run_gates(
            session,
            gates_to_run,
            engine_adapter=engine_adapter,
            engine_kwargs=engine_kwargs or {},
            timeout=gate_timeout,
        )
        session["gate_results"].extend(results)
        add_event(session, "gates_executed", {
            "iteration": iteration,
            "results": len(results),
        })

        # Collect all findings
        all_findings: list[dict] = []
        for r in results:
            all_findings.extend(r.get("findings", []))

        # --- Phase D: Noise suppression ---
        deduped = merge_duplicates(all_findings)
        suppressed = suppress_seen(deduped, all_previous_findings)
        calibrated = calibrate(suppressed)

        # Check if all gates passed
        if not results:
            transition(session, "gates_failed")
            transition(session, "failed_terminal", reason="no gate results")
            session["final_outcome"] = {
                "action": "block",
                "state": "failed_terminal",
                "stop_reason": "no gate results — zero verification",
                "iteration": iteration,
            }
            add_event(session, "session_failed", session["final_outcome"])
            return session
        all_passed = all(r.get("status") == "pass" for r in results)

        if all_passed:
            transition(session, "passed")
            session["final_outcome"] = {
                "action": "pass",
                "state": "passed",
                "iteration": iteration,
                "total_findings": len(all_findings),
                "findings_after_noise": len(calibrated),
            }
            add_event(session, "session_passed", session["final_outcome"])
            return session

        # --- Phase C: Retry logic ---
        brief = translate(results, contracts, retry_count=iteration + 1)
        session["retry_briefs"].append(brief)
        previous_briefs.append(brief)

        # Check stop conditions
        stop, reason = should_stop(session, max_retries=max_retries)
        if stop:
            if reason == "all gates passing — no retry needed":
                transition(session, "passed")
                session["final_outcome"] = {
                    "action": "pass",
                    "state": "passed",
                    "stop_reason": reason,
                    "iteration": iteration,
                    "total_findings": len(all_findings),
                }
                add_event(session, "session_passed", session["final_outcome"])
                return session
            transition(session, "gates_failed")
            transition(session, "failed_terminal", reason=reason)
            session["final_outcome"] = {
                "action": "block",
                "state": "failed_terminal",
                "stop_reason": reason,
                "iteration": iteration,
                "total_findings": len(all_findings),
                "last_brief": brief,
            }
            add_event(session, "session_failed", session["final_outcome"])
            return session

        # Check strategy
        strat = select_strategy(brief, previous_briefs[:-1])
        if strat["action"] in ("abort", "escalate"):
            transition(session, "gates_failed")
            transition(session, "failed_terminal", reason=f"strategy: {strat['action']}")
            session["final_outcome"] = {
                "action": "block",
                "state": "failed_terminal",
                "stop_reason": f"strategy {strat['action']}: {strat.get('modifications', [])}",
                "iteration": iteration,
            }
            add_event(session, "session_failed", session["final_outcome"])
            return session

        # Transition to retrying
        transition(session, "gates_failed")
        transition(session, "retrying")
        add_event(session, "retrying", {
            "iteration": iteration,
            "strategy": strat["strategy"],
            "brief_id": brief.get("retry_id"),
        })

        all_previous_findings.extend(all_findings)

        # Use re_run_gates from strategy if specified, else fall back to full gate list
        re_run = strat.get("re_run_gates")
        if re_run:
            gates_to_run = [
                g for g in gate_plan["selected_gates"]
                if g["gate_id"] in re_run
            ]
        else:
            gates_to_run = gate_plan["selected_gates"]

    # Exhausted all iterations
    if session["state"] == "retrying":
        transition(session, "gates_failed")
    if session["state"] != "failed_terminal":
        transition(session, "failed_terminal", reason="max iterations exhausted")
    session["final_outcome"] = {
        "action": "block",
        "state": "failed_terminal",
        "stop_reason": "max iterations exhausted",
    }
    return session
