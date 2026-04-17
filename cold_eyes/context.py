"""Context retrieval for deep review — recent commits and co-changed files."""

from cold_eyes.git import git_cmd, estimate_tokens, GitCommandError


def _recent_commits(filepath, limit=5):
    """Recent commit subjects for a file. Returns list of strings."""
    try:
        log = git_cmd("log", f"-{limit}", "--oneline", "--", filepath)
        return [line.strip() for line in log.split("\n") if line.strip()]
    except GitCommandError:
        return []


def _co_changed_files(filepath, limit=5):
    """Files frequently committed alongside this file. Returns sorted list."""
    try:
        log = git_cmd(
            "log", f"-{limit}", "--name-only", "--pretty=format:", "--",
            filepath,
        )
        co_files = set()
        for line in log.split("\n"):
            line = line.strip()
            if line and line != filepath:
                co_files.add(line)
        return sorted(co_files)[:10]
    except GitCommandError:
        return []


def build_context(files, max_tokens=2000):
    """Build context string from git history for changed files.

    Args:
        files: list of changed file paths.
        max_tokens: token budget for context section.

    Returns dict with context_text, context_summary, token_count.
    """
    if not files:
        return {"context_text": "", "context_summary": "no files", "token_count": 0}

    sections = []
    for f in files:
        parts = []
        commits = _recent_commits(f)
        if commits:
            parts.append(f"  Recent commits for {f}:")
            for c in commits:
                parts.append(f"    {c}")

        co = _co_changed_files(f)
        if co:
            parts.append(f"  Co-changed files: {', '.join(co)}")

        if parts:
            sections.append("\n".join(parts))

    if not sections:
        return {"context_text": "", "context_summary": "no git history", "token_count": 0}

    context_text = (
        "[Cold Eyes: Context for review]\n"
        + "\n".join(sections)
        + "\n[End context]\n"
    )

    # Enforce token budget (reserve space for the truncation notice so the
    # final token_count stays within max_tokens — same pattern as git.py).
    token_count = estimate_tokens(context_text)
    if token_count > max_tokens:
        truncation_notice = "\n[context truncated]\n"
        notice_tokens = estimate_tokens(truncation_notice)
        body_budget = max(max_tokens - notice_tokens, 0)
        ascii_count = sum(1 for c in context_text if ord(c) < 128)
        non_ascii_count = len(context_text) - ascii_count
        ratio = (ascii_count * 4 + non_ascii_count) / max(len(context_text), 1)
        char_limit = int(body_budget * ratio)
        context_text = context_text[:char_limit] + truncation_notice
        token_count = estimate_tokens(context_text)
        # Belt-and-suspenders: if ratio rounding still overshoots, trim body.
        if token_count > max_tokens and char_limit > 0:
            overshoot_tokens = token_count - max_tokens
            overshoot_chars = max(int(overshoot_tokens * ratio) + 1, 1)
            char_limit = max(char_limit - overshoot_chars, 0)
            context_text = context_text[:char_limit] + truncation_notice
            token_count = estimate_tokens(context_text)

    file_count = len(sections)
    return {
        "context_text": context_text,
        "context_summary": f"recent commits for {file_count} file(s)",
        "token_count": token_count,
    }
