"""Session store — JSONL-based persistence for session records."""

import json
import os
import tempfile

from cold_eyes.session.schema import validate_session

_DEFAULT_DIR = os.path.join(os.path.expanduser("~"), ".claude", "cold-review-sessions")


class SessionStore:
    """Append-only JSONL store for session records.

    Each session is one JSON line in ``sessions.jsonl``.
    Gate results and retry attempts are embedded inside the session record
    (not separate files) to keep the store simple.
    """

    def __init__(self, path: str | None = None):
        self._dir = path or _DEFAULT_DIR
        self._file = os.path.join(self._dir, "sessions.jsonl")

    # -- write ---------------------------------------------------------------

    def save(self, session: dict) -> None:
        """Append (or overwrite) a session to the store."""
        ok, errors = validate_session(session)
        if not ok:
            raise ValueError(f"invalid session: {errors}")
        lines = self._read_all()
        # Replace existing session or append new one
        found = False
        for i, line in enumerate(lines):
            if line.get("session_id") == session["session_id"]:
                lines[i] = session
                found = True
                break
        if not found:
            lines.append(session)
        self._write_all(lines)

    def update(self, session: dict) -> None:
        """Update an existing session. Raises if not found."""
        lines = self._read_all()
        for i, line in enumerate(lines):
            if line.get("session_id") == session["session_id"]:
                ok, errors = validate_session(session)
                if not ok:
                    raise ValueError(f"invalid session: {errors}")
                lines[i] = session
                self._write_all(lines)
                return
        raise KeyError(f"session not found: {session.get('session_id')}")

    # -- read ----------------------------------------------------------------

    def load(self, session_id: str) -> dict:
        """Load a single session by ID. Raises KeyError if not found."""
        for line in self._read_all():
            if line.get("session_id") == session_id:
                return line
        raise KeyError(f"session not found: {session_id}")

    def list_sessions(self, last_n: int = 20) -> list[dict]:
        """Return the most recent *last_n* sessions (newest first)."""
        all_sessions = self._read_all()
        return list(reversed(all_sessions[-last_n:]))

    # -- internals -----------------------------------------------------------

    def _read_all(self) -> list[dict]:
        if not os.path.isfile(self._file):
            return []
        entries: list[dict] = []
        with open(self._file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries

    def _write_all(self, entries: list[dict]) -> None:
        os.makedirs(self._dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for entry in entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            os.replace(tmp_path, self._file)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
