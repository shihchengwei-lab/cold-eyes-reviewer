"""Metrics collector — session and aggregate metrics."""


def collect_metrics(session: dict) -> dict:
    """Collect metrics from a single completed session.

    Returns a dict with key performance indicators.
    """
    gate_results = session.get("gate_results", [])
    retry_briefs = session.get("retry_briefs", [])
    contracts = session.get("contracts", [])
    final = session.get("final_outcome", {})

    total_findings = sum(len(gr.get("findings", [])) for gr in gate_results)
    total_gates = len(gate_results)
    passed_gates = sum(1 for gr in gate_results if gr.get("status") == "pass")
    failed_gates = sum(1 for gr in gate_results if gr.get("status") == "fail")
    total_duration = sum(gr.get("duration_ms", 0) for gr in gate_results)

    return {
        "session_id": session.get("session_id", ""),
        "final_state": final.get("state", session.get("state", "")),
        "total_gates_run": total_gates,
        "gates_passed": passed_gates,
        "gates_failed": failed_gates,
        "total_findings": total_findings,
        "findings_after_noise": final.get("findings_after_noise", total_findings),
        "retry_count": len(retry_briefs),
        "contracts_count": len(contracts),
        "total_duration_ms": total_duration,
        "iterations": final.get("iteration", 0),
    }


def aggregate_metrics(sessions: list[dict]) -> dict:
    """Aggregate metrics across multiple sessions.

    Returns summary statistics.
    """
    if not sessions:
        return {"session_count": 0}

    metrics = [collect_metrics(s) for s in sessions]
    n = len(metrics)

    total_retries = sum(m["retry_count"] for m in metrics)
    total_gates = sum(m["total_gates_run"] for m in metrics)
    passed_sessions = sum(1 for m in metrics if m["final_state"] == "passed")
    failed_sessions = sum(1 for m in metrics if m["final_state"] == "failed_terminal")
    aborted_sessions = sum(1 for m in metrics if m["final_state"] == "aborted")
    completed = passed_sessions + failed_sessions

    return {
        "session_count": n,
        "passed_sessions": passed_sessions,
        "failed_sessions": failed_sessions,
        "aborted_sessions": aborted_sessions,
        "pass_rate": round(passed_sessions / completed, 2) if completed else 0.0,
        "total_retries": total_retries,
        "avg_retries": round(total_retries / n, 1) if n else 0.0,
        "total_gates_run": total_gates,
        "avg_gates_per_session": round(total_gates / n, 1) if n else 0.0,
        "total_findings": sum(m["total_findings"] for m in metrics),
        "avg_findings_per_session": round(sum(m["total_findings"] for m in metrics) / n, 1) if n else 0.0,
    }
