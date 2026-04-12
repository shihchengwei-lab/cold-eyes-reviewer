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

    # Enforce token budget
    token_count = estimate_tokens(context_text)
    if token_count > max_tokens:
        char_limit = max_tokens * 2
        context_text = context_text[:char_limit] + "\n[context truncated]\n"
        token_count = max_tokens

    file_count = len(sections)
    return {
        "context_text": context_text,
        "context_summary": f"recent commits for {file_count} file(s)",
        "token_count": token_count,
    }
