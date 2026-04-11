"""Tests for cold_eyes.override — one-time override tokens."""

import json
import os
import time

import pytest

from cold_eyes.override import arm_override, consume_override, TOKEN_DIR, _repo_hash


class TestArmOverride:

    def test_creates_token_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cold_eyes.override.TOKEN_DIR", str(tmp_path))
        result = arm_override("/some/repo", "false_positive")
        assert result["action"] == "arm-override"
        assert result["reason"] == "false_positive"
        assert os.path.isfile(result["token_path"])
        with open(result["token_path"]) as f:
            token = json.load(f)
        assert token["repo_root"] == os.path.normpath("/some/repo")
        assert "nonce" in token

    def test_default_ttl_10_minutes(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cold_eyes.override.TOKEN_DIR", str(tmp_path))
        result = arm_override("/repo", "test")
        from datetime import datetime
        created = datetime.fromisoformat(result["created_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(result["expires_at"].replace("Z", "+00:00"))
        delta = (expires - created).total_seconds()
        assert 590 <= delta <= 610  # ~10 minutes


class TestConsumeOverride:

    def test_consume_returns_reason_deletes_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cold_eyes.override.TOKEN_DIR", str(tmp_path))
        arm_override("/repo", "bad_lint_rule")
        ok, reason = consume_override("/repo")
        assert ok is True
        assert reason == "bad_lint_rule"
        # File should be deleted
        token_path = os.path.join(str(tmp_path), f"{_repo_hash('/repo')}.json")
        assert not os.path.exists(token_path)

    def test_double_consume_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cold_eyes.override.TOKEN_DIR", str(tmp_path))
        arm_override("/repo", "once")
        ok1, _ = consume_override("/repo")
        ok2, reason2 = consume_override("/repo")
        assert ok1 is True
        assert ok2 is False
        assert reason2 == ""

    def test_expired_token_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cold_eyes.override.TOKEN_DIR", str(tmp_path))
        arm_override("/repo", "test", ttl_minutes=0)
        # ttl=0 means it expires immediately
        time.sleep(0.1)
        ok, reason = consume_override("/repo")
        assert ok is False

    def test_repo_mismatch_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cold_eyes.override.TOKEN_DIR", str(tmp_path))
        arm_override("/repo/a", "test")
        # Try to consume with different repo
        ok, reason = consume_override("/repo/b")
        assert ok is False

    def test_no_token_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cold_eyes.override.TOKEN_DIR", str(tmp_path))
        ok, reason = consume_override("/repo")
        assert ok is False
        assert reason == ""

    def test_empty_repo_root_returns_false(self):
        ok, reason = consume_override("")
        assert ok is False
