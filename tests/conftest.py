"""Shared fixtures for cold-eyes-reviewer tests."""

import os
import importlib
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SCRIPTS_DIR = PROJECT_ROOT
SHELL_SCRIPT = os.path.join(SCRIPTS_DIR, "cold-review.sh")
HELPER_SCRIPT = os.path.join(SCRIPTS_DIR, "cold-review-helper.py")


def load_helper():
    """Import cold-review-helper.py as a module (hyphenated filename)."""
    spec = importlib.util.spec_from_file_location(
        "cold_review_helper",
        HELPER_SCRIPT,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def helper():
    return load_helper()


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


@pytest.fixture
def helper_script():
    return HELPER_SCRIPT
