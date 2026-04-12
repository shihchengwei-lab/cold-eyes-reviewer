"""Gate orchestrator — execute selected gates and collect results."""

import json
import subprocess
import time

from cold_eyes.gates.catalog import get_gate
from cold_eyes.gates.result import normalize_result
from cold_eyes.type_defs import GateResult


def run_gates(
    session: dict,
    selected_gates: list[dict],
    *,
    engine_adapter=None,
    engine_kwargs: dict | None = None,
    timeout: int = 120,
) -> list[GateResult]:
    """Execute gates sequentially and return normalised results.

    Parameters
    ----------
    session : dict
        The current SessionRecord (used for context).
    selected_gates : list[dict]
        Output from ``select_gates()`` — each has ``gate_id`` and ``blocking``.
    engine_adapter : ModelAdapter, optional
        If provided, the ``llm_review`` gate uses this adapter instead of
        calling ``engine.run()`` (useful for testing with MockAdapter).
    engine_kwargs : dict, optional
        Extra kwargs forwarded to ``engine.run()`` for the llm_review gate.
    timeout : int
        Seconds before an external gate subprocess is killed.

    Returns
    -------
    list[GateResult]
    """
    results: list[GateResult] = []

    for entry in selected_gates:
        gate_id = entry["gate_id"]
        blocking = entry.get("blocking", "soft")

        if gate_id == "llm_review":
            result = _run_llm_review(
                session, blocking, engine_adapter, engine_kwargs or {}
            )
        else:
            gate_def = get_gate(gate_id)
            result = _run_external(gate_id, gate_def, blocking, timeout)

        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Gate runners
# ---------------------------------------------------------------------------

def _run_llm_review(
    session: dict,
    blocking: str,
    adapter,
    engine_kwargs: dict,
) -> GateResult:
    """Run the v1 engine as a gate.  Returns GateResult."""
    t0 = time.monotonic()
    try:
        from cold_eyes.engine import run as engine_run
        kwargs = dict(engine_kwargs)
        if adapter is not None:
            kwargs["adapter"] = adapter
        outcome = engine_run(**kwargs)
        raw = json.dumps(outcome, ensure_ascii=False)
        exit_code = 0 if outcome.get("action") != "block" else 1
    except Exception as exc:
        raw = str(exc)
        exit_code = 1

    duration = int((time.monotonic() - t0) * 1000)
    return normalize_result("llm_review", raw, exit_code, duration, blocking)


def _run_external(
    gate_id: str,
    gate_def: dict,
    blocking: str,
    timeout: int,
) -> GateResult:
    """Run an external tool gate via subprocess."""
    cmd = _build_command(gate_id, gate_def)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
        )
        raw = proc.stdout + proc.stderr
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        raw = f"gate {gate_id} timed out after {timeout}s"
        exit_code = 1
    except FileNotFoundError:
        raw = f"tool not found: {cmd[0]}"
        exit_code = 1

    duration = int((time.monotonic() - t0) * 1000)
    return normalize_result(gate_id, raw, exit_code, duration, blocking)


def _build_command(gate_id: str, gate_def: dict) -> list[str]:
    """Build the subprocess command for a gate."""
    tool = gate_def.get("tool_command", gate_id)
    _COMMANDS: dict[str, list[str]] = {
        "test_runner": [tool, "--tb=short", "-q"],
        "lint_checker": [tool, "check", "."],
        "type_checker": [tool, "."],
        "build_checker": [tool, "check", "--quiet"],
    }
    return _COMMANDS.get(gate_id, [tool])
