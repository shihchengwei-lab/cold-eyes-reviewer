"""Prompt template loading and language substitution."""

import os

from cold_eyes.constants import PROMPT_TEMPLATE


def build_prompt_text(language=None):
    """Assemble system prompt from template + language env var. Return string."""
    if language is None:
        language = os.environ.get("COLD_REVIEW_LANGUAGE", "\u7e41\u9ad4\u4e2d\u6587\uff08\u53f0\u7063\uff09")

    try:
        with open(PROMPT_TEMPLATE, "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        return "You are Cold Eyes, a zero-context reviewer. Review the diff. Output JSON: {pass, issues, summary}."

    return template.replace("{language}", language)
