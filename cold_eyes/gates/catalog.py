"""Gate catalog — registry of available verification gates."""

import shutil
from typing import TypedDict


class GateDefinition(TypedDict, total=False):
    """Metadata for a single verification gate."""
    gate_id: str
    gate_name: str
    gate_type: str           # "builtin" | "external"
    cost_class: str          # "free" | "cheap" | "expensive"
    blocking_mode: str       # "hard" | "soft"
    applicable_risk_categories: list[str]
    supports_auto_retry: bool
    requires_context: bool
    tool_command: str         # e.g. "pytest", "ruff", used for availability check


# ---------------------------------------------------------------------------
# Built-in gate definitions
# ---------------------------------------------------------------------------

_GATES: dict[str, GateDefinition] = {
    "llm_review": GateDefinition(
        gate_id="llm_review",
        gate_name="LLM Code Review",
        gate_type="builtin",
        cost_class="expensive",
        blocking_mode="hard",
        applicable_risk_categories=[],   # all categories
        supports_auto_retry=False,
        requires_context=True,
        tool_command="claude",
    ),
    "test_runner": GateDefinition(
        gate_id="test_runner",
        gate_name="Test Runner",
        gate_type="external",
        cost_class="cheap",
        blocking_mode="hard",
        applicable_risk_categories=[],
        supports_auto_retry=True,
        requires_context=False,
        tool_command="pytest",
    ),
    "lint_checker": GateDefinition(
        gate_id="lint_checker",
        gate_name="Lint Checker",
        gate_type="external",
        cost_class="free",
        blocking_mode="soft",
        applicable_risk_categories=[],
        supports_auto_retry=True,
        requires_context=False,
        tool_command="ruff",
    ),
    "type_checker": GateDefinition(
        gate_id="type_checker",
        gate_name="Type Checker",
        gate_type="external",
        cost_class="cheap",
        blocking_mode="soft",
        applicable_risk_categories=[],
        supports_auto_retry=True,
        requires_context=False,
        tool_command="mypy",
    ),
    "build_checker": GateDefinition(
        gate_id="build_checker",
        gate_name="Build Checker",
        gate_type="external",
        cost_class="cheap",
        blocking_mode="hard",
        applicable_risk_categories=[],
        supports_auto_retry=True,
        requires_context=False,
        tool_command="pip",
    ),
}


def list_gates() -> list[GateDefinition]:
    """Return all registered gate definitions."""
    return list(_GATES.values())


def get_gate(gate_id: str) -> GateDefinition:
    """Return a gate definition by ID. Raises KeyError if not found."""
    if gate_id not in _GATES:
        raise KeyError(f"unknown gate: {gate_id}")
    return _GATES[gate_id]


def is_available(gate_id: str) -> bool:
    """Check if the tool for *gate_id* is available on the system."""
    gate = _GATES.get(gate_id)
    if gate is None:
        return False
    cmd = gate.get("tool_command", "")
    if not cmd:
        return False
    return shutil.which(cmd) is not None


def available_gates() -> list[str]:
    """Return gate IDs whose tools are available on this system."""
    return [gid for gid in _GATES if is_available(gid)]
