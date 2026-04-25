"""Low-weight user intent extraction for hook-driven reviews.

The intent capsule is deliberately small and low authority. It helps the
reviewer notice obvious "the diff contradicts the user's recent goal" cases,
but policy still requires diff evidence before an intent finding can block.
"""

from __future__ import annotations

import json
import os
import re


DEFAULT_INTENT_MAX_CHARS = 1200
MAX_HOOK_INPUT_BYTES = 1_048_576
MAX_TRANSCRIPT_BYTES = 262_144
MAX_USER_MESSAGES = 3

_OFF_VALUES = {"0", "false", "no", "off"}
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def is_enabled(value: str | None, default: bool = True) -> bool:
    """Return whether an optional env-style setting is enabled."""
    if value is None or value == "":
        return default
    return value.strip().lower() not in _OFF_VALUES


def load_intent_capsule(
    hook_input_path: str | None = None,
    *,
    enabled: bool = True,
    max_chars: int = DEFAULT_INTENT_MAX_CHARS,
) -> dict:
    """Load a low-weight intent capsule from Claude Code hook input.

    Returns a small dict with ``status`` and optional ``summary``. All failures
    are soft skips so intent extraction can never break review execution.
    """
    if not enabled:
        return {"status": "disabled", "summary": ""}
    if not hook_input_path:
        return {"status": "missing_hook_input", "summary": ""}

    try:
        raw = _read_limited_text(hook_input_path, MAX_HOOK_INPUT_BYTES)
    except OSError as exc:
        return {"status": "unreadable_hook_input", "summary": "", "error": str(exc)}

    try:
        hook_input = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {"status": "malformed_hook_input", "summary": ""}
    if not isinstance(hook_input, dict):
        return {"status": "malformed_hook_input", "summary": ""}

    inline = _extract_inline_user_text(hook_input)
    if inline:
        return _capsule_from_messages([inline], max_chars, source="hook_input")

    transcript_path = _transcript_path(hook_input)
    if not transcript_path:
        return {"status": "missing_transcript", "summary": ""}
    transcript_path = os.path.expanduser(transcript_path)
    if not os.path.isfile(transcript_path):
        return {"status": "missing_transcript", "summary": "", "path": transcript_path}

    try:
        transcript_text = _read_tail_text(transcript_path, MAX_TRANSCRIPT_BYTES)
    except OSError as exc:
        return {
            "status": "unreadable_transcript",
            "summary": "",
            "path": transcript_path,
            "error": str(exc),
        }

    messages = _extract_user_messages(transcript_text)
    if not messages:
        return {"status": "empty", "summary": "", "path": transcript_path}
    capsule = _capsule_from_messages(messages[-MAX_USER_MESSAGES:], max_chars, source="transcript")
    capsule["path"] = transcript_path
    capsule["message_count"] = len(messages)
    return capsule


def intent_prompt_block(capsule: dict | None) -> str:
    """Return the prompt text for a found intent capsule."""
    if not capsule or capsule.get("status") != "found" or not capsule.get("summary"):
        return ""
    return (
        "\n[Cold Eyes: User intent capsule - low weight]\n"
        "This is a small extract of recent user goals. Treat it as a hint only. "
        "It must not override diff evidence. Only report an intent mismatch when "
        "the visible diff clearly contradicts this goal and your issue evidence cites the diff.\n"
        f"{capsule['summary']}\n"
    )


def _transcript_path(hook_input: dict) -> str:
    for key in ("transcript_path", "transcriptPath", "transcript"):
        value = hook_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_inline_user_text(hook_input: dict) -> str:
    for key in ("user_prompt", "prompt", "user_message"):
        value = hook_input.get(key)
        if isinstance(value, str) and value.strip():
            return _sanitize(value)
    return ""


def _read_limited_text(path: str, max_bytes: int) -> str:
    with open(path, "rb") as f:
        data = f.read(max_bytes + 1)
    return data[:max_bytes].decode("utf-8", errors="replace")


def _read_tail_text(path: str, max_bytes: int) -> str:
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
        data = f.read(max_bytes)
    text = data.decode("utf-8", errors="replace")
    if size > max_bytes:
        first_newline = text.find("\n")
        if first_newline >= 0:
            text = text[first_newline + 1:]
    return text


def _extract_user_messages(transcript_text: str) -> list[str]:
    messages: list[str] = []
    for line in transcript_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        role, content = _role_and_content(obj)
        if role != "user":
            continue
        text = _flatten_content(content)
        if text:
            messages.append(_sanitize(text))
    return [m for m in messages if m]


def _role_and_content(obj: dict) -> tuple[str, object]:
    if not isinstance(obj, dict):
        return "", ""
    message = obj.get("message")
    if isinstance(message, dict):
        role = str(message.get("role") or obj.get("role") or obj.get("type") or "")
        return role.lower(), message.get("content", "")
    role = str(obj.get("role") or obj.get("type") or obj.get("speaker") or "")
    return role.lower(), obj.get("content", obj.get("text", ""))


def _flatten_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        for key in ("text", "content", "message"):
            value = content.get(key)
            if isinstance(value, str):
                return value
        return ""
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def _capsule_from_messages(messages: list[str], max_chars: int, source: str) -> dict:
    max_chars = _safe_max_chars(max_chars)
    joined = "\n\n".join(_sanitize(m) for m in messages if _sanitize(m))
    summary = _trim(joined, max_chars)
    if not summary:
        return {"status": "empty", "summary": "", "source": source}
    return {
        "status": "found",
        "summary": summary,
        "source": source,
        "truncated": len(joined) > max_chars,
    }


def _safe_max_chars(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_INTENT_MAX_CHARS
    return max(200, min(parsed, 4000))


def _trim(text: str, max_chars: int) -> str:
    text = _sanitize(text)
    if len(text) <= max_chars:
        return text
    return text[-max_chars:].lstrip()


def _sanitize(text: str) -> str:
    text = _CONTROL_CHARS.sub("", str(text))
    lines = [line.rstrip() for line in text.replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line.strip()).strip()
