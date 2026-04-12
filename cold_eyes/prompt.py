"""Prompt template loading and language substitution."""

import os

from cold_eyes.constants import PROMPT_TEMPLATE, PROMPT_TEMPLATE_SHALLOW


def build_prompt_text(language=None, depth="deep"):
    """Assemble system prompt from template + language env var. Return string.

    depth: 'deep' (default) or 'shallow'. Selects the prompt template.
    """
    if language is None:
        language = os.environ.get("COLD_REVIEW_LANGUAGE", "\u7e41\u9ad4\u4e2d\u6587\uff08\u53f0\u7063\uff09")

    template_path = PROMPT_TEMPLATE_SHALLOW if depth == "shallow" else PROMPT_TEMPLATE

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        if depth == "shallow":
            return ("You are Cold Eyes (shallow mode). "
                    "Only report critical security and crash bugs. "
                    "Output JSON: {pass, issues, summary}.")
        return ("You are Cold Eyes, a zero-context reviewer. "
                "Review the diff. Output JSON: {pass, issues, summary}.")

    return template.replace("{language}", language)
