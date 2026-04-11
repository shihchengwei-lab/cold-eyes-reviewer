"""Git operations and diff construction."""

import os
import subprocess


def git_cmd(*args):
    """Run a git command, return stdout or empty string on failure."""
    r = subprocess.run(
        ["git"] + list(args), capture_output=True, text=True
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def collect_files(scope="working"):
    """Return (all_files sorted list, untracked set).

    Scopes:
      working — staged + unstaged + untracked (default)
      staged  — only staged changes
      head    — diff against HEAD (staged + unstaged, no untracked)
    """
    if scope == "staged":
        staged = set(filter(None, git_cmd("diff", "--cached", "--name-only").split("\n")))
        return sorted(staged), set()
    elif scope == "head":
        head = set(filter(None, git_cmd("diff", "HEAD", "--name-only").split("\n")))
        return sorted(head), set()
    else:  # working
        staged = set(filter(None, git_cmd("diff", "--cached", "--name-only").split("\n")))
        unstaged = set(filter(None, git_cmd("diff", "--name-only").split("\n")))
        untracked = set(filter(None, git_cmd("ls-files", "--others", "--exclude-standard").split("\n")))
        return sorted(staged | unstaged | untracked), untracked


def is_binary(filepath):
    """True if file contains null bytes in first 512 bytes."""
    try:
        with open(filepath, "rb") as f:
            return b"\x00" in f.read(512)
    except (OSError, IOError):
        return False


def build_diff(ranked_files, untracked, max_tokens=12000, scope="working"):
    """Build token-budgeted diff.

    Returns (diff_text, file_count, token_count, truncated, skipped_files).
    Token estimate: len(text) // 4.
    """
    remaining = max_tokens
    parts = []
    file_count = 0
    skipped = []

    for f in ranked_files:
        if remaining <= 0:
            skipped.append(f)
            continue

        if f in untracked:
            if is_binary(f):
                skipped.append(f"{f} (binary)")
                continue
            try:
                with open(f, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
            except (OSError, IOError):
                skipped.append(f"{f} (unreadable)")
                continue
            chunk = f"=== NEW FILE: {f} ===\n{content}"
        else:
            if scope == "staged":
                chunk = git_cmd("diff", "--cached", "--", f)
            elif scope == "head":
                chunk = git_cmd("diff", "HEAD", "--", f)
            else:  # working
                staged = git_cmd("diff", "--cached", "--", f)
                unstaged = git_cmd("diff", "--", f)
                chunk = f"{staged}\n{unstaged}".strip()

        if not chunk:
            continue

        chunk_tokens = len(chunk) // 4
        if chunk_tokens > remaining:
            char_limit = remaining * 4
            chunk = chunk[:char_limit] + f"\n[truncated: {f}]"
            chunk_tokens = remaining

        parts.append(chunk)
        file_count += 1
        remaining -= chunk_tokens

    diff_text = "\n".join(parts)
    total_tokens = max_tokens - remaining
    truncated = len(skipped) > 0

    if truncated:
        notice = f"\n\n[Cold Eyes: diff truncated at ~{max_tokens} tokens. Skipped files:\n"
        for s in skipped:
            notice += f"  {s}\n"
        notice += "]"
        diff_text += notice

    return diff_text, file_count, total_tokens, truncated, skipped
