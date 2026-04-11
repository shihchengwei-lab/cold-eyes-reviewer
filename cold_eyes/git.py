"""Git operations and diff construction."""

import os
import subprocess


class GitCommandError(RuntimeError):
    """A git command exited with non-zero status."""
    def __init__(self, cmd, returncode, stderr=""):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"git {' '.join(cmd)} failed (exit {returncode}): {stderr[:200]}"
        )


class ConfigError(RuntimeError):
    """A configuration-level problem (missing base, bad scope, etc.)."""
    pass


def git_cmd(*args):
    """Run a git command, return stdout.  Raise GitCommandError on failure."""
    r = subprocess.run(
        ["git"] + list(args), capture_output=True, text=True, encoding="utf-8"
    )
    if r.returncode != 0:
        raise GitCommandError(list(args), r.returncode, r.stderr.strip())
    return r.stdout.strip()


def collect_files(scope="working", base=None):
    """Return (all_files sorted list, untracked set).

    Scopes:
      working  — staged + unstaged + untracked (default)
      staged   — only staged changes
      head     — diff against HEAD (staged + unstaged, no untracked)
      pr-diff  — diff of current branch vs base (requires base arg)
    """
    if scope == "pr-diff":
        if not base:
            raise ConfigError("pr-diff scope requires --base")
        pr = set(filter(None, git_cmd(
            "diff", f"{base}...HEAD", "--name-only").split("\n")))
        return sorted(pr), set()
    elif scope == "staged":
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


def build_diff(ranked_files, untracked, max_tokens=12000, scope="working",
               base=None):
    """Build token-budgeted diff.

    Returns dict with keys:
      diff_text, file_count, token_count, truncated,
      partial_files, skipped_budget, skipped_binary, skipped_unreadable
    """
    remaining = max_tokens
    parts = []
    file_count = 0
    partial_files = []
    skipped_budget = []
    skipped_binary = []
    skipped_unreadable = []

    for f in ranked_files:
        if remaining <= 0:
            skipped_budget.append(f)
            continue

        if f in untracked:
            if is_binary(f):
                skipped_binary.append(f)
                continue
            try:
                with open(f, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
            except (OSError, IOError):
                skipped_unreadable.append(f)
                continue
            chunk = f"=== NEW FILE: {f} ===\n{content}"
        else:
            if scope == "pr-diff" and base:
                chunk = git_cmd("diff", f"{base}...HEAD", "--", f)
            elif scope == "staged":
                chunk = git_cmd("diff", "--cached", "--", f)
            elif scope == "head":
                chunk = git_cmd("diff", "HEAD", "--", f)
            else:  # working
                staged = git_cmd("diff", "--cached", "--", f)
                unstaged = git_cmd("diff", "--", f)
                chunk = f"{staged}\n{unstaged}".strip()

        if not chunk:
            continue

        chunk_tokens = len(chunk.encode("utf-8")) // 4
        if chunk_tokens > remaining:
            char_limit = remaining * 4
            chunk = chunk[:char_limit] + f"\n[truncated: {f}]"
            chunk_tokens = remaining
            partial_files.append(f)

        parts.append(chunk)
        file_count += 1
        remaining -= chunk_tokens

    diff_text = "\n".join(parts)
    total_tokens = max_tokens - remaining
    truncated = bool(partial_files or skipped_budget or skipped_binary or skipped_unreadable)

    if truncated:
        notice_parts = []
        if partial_files:
            notice_parts.append("Partial (cut mid-file): " + ", ".join(partial_files))
        if skipped_budget:
            notice_parts.append("Skipped (budget): " + ", ".join(skipped_budget))
        if skipped_binary:
            notice_parts.append("Skipped (binary): " + ", ".join(skipped_binary))
        if skipped_unreadable:
            notice_parts.append("Skipped (unreadable): " + ", ".join(skipped_unreadable))
        notice = f"\n\n[Cold Eyes: diff truncated at ~{max_tokens} tokens.\n"
        for p in notice_parts:
            notice += f"  {p}\n"
        notice += "]"
        diff_text += notice

    return {
        "diff_text": diff_text,
        "file_count": file_count,
        "token_count": total_tokens,
        "truncated": truncated,
        "partial_files": partial_files,
        "skipped_budget": skipped_budget,
        "skipped_binary": skipped_binary,
        "skipped_unreadable": skipped_unreadable,
    }
