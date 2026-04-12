"""Tests for cold_eyes.gates.catalog."""

from unittest.mock import patch

from cold_eyes.gates.catalog import (
    available_gates,
    get_gate,
    is_available,
    list_gates,
)
import pytest


class TestListGates:
    def test_returns_list(self):
        gates = list_gates()
        assert isinstance(gates, list)
        assert len(gates) >= 5

    def test_each_gate_has_required_fields(self):
        for g in list_gates():
            assert "gate_id" in g
            assert "gate_name" in g
            assert "gate_type" in g
            assert "cost_class" in g
            assert "blocking_mode" in g


class TestGetGate:
    def test_known_gate(self):
        g = get_gate("llm_review")
        assert g["gate_name"] == "LLM Code Review"
        assert g["cost_class"] == "expensive"

    def test_unknown_gate_raises(self):
        with pytest.raises(KeyError, match="unknown gate"):
            get_gate("nonexistent")


class TestIsAvailable:
    @patch("cold_eyes.gates.catalog.shutil.which", return_value="/usr/bin/pytest")
    def test_available_tool(self, mock_which):
        assert is_available("test_runner") is True
        mock_which.assert_called_with("pytest")

    @patch("cold_eyes.gates.catalog.shutil.which", return_value=None)
    def test_unavailable_tool(self, mock_which):
        assert is_available("type_checker") is False

    def test_unknown_gate(self):
        assert is_available("ghost_gate") is False


class TestAvailableGates:
    @patch("cold_eyes.gates.catalog.shutil.which", return_value="/usr/bin/tool")
    def test_all_available(self, mock_which):
        gates = available_gates()
        assert len(gates) >= 5

    @patch("cold_eyes.gates.catalog.shutil.which", return_value=None)
    def test_none_available(self, mock_which):
        assert available_gates() == []
