"""Shared fixtures for cold-eyes-reviewer tests."""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SCRIPTS_DIR = PROJECT_ROOT
SHELL_SCRIPT = os.path.join(SCRIPTS_DIR, "cold-review.sh")

# Add project root to sys.path so `import cold_eyes` works
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture
def fixture_path():
    """Return a helper to resolve fixture file paths."""
    def _resolve(name):
        return os.path.join(FIXTURES_DIR, name)
    return _resolve


@pytest.fixture
def scripts_dir():
    return SCRIPTS_DIR


@pytest.fixture
def shell_script():
    return SHELL_SCRIPT


@pytest.fixture(autouse=True)
def disable_local_checks_by_default(monkeypatch):
    """Keep engine tests focused unless a test opts into local checks."""
    monkeypatch.setenv("COLD_REVIEW_CHECKS", "off")
