"""Prompt template loading and language substitution."""

import os
import re

from cold_eyes.constants import PROMPT_TEMPLATE, PROMPT_TEMPLATE_SHALLOW

# Allow alphanumeric, spaces, hyphens, parens, and common CJK/unicode letters
_LANG_ALLOW = re.compile(r'[^\w\s\-\(\)\u3000-\u9fff\uf900-\ufaff]', re.UNICODE)


def _sanitize_language(value: str) -> str:
    """Sanitize language string to prevent prompt injection."""
    value = value[:50]
    # Strip newlines, carriage returns, and control characters
    value = value.replace('\n', '').replace('\r', '')
    value = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', value)
    # Remove characters outside the allow list
    value = _LANG_ALLOW.sub('', value)
    return value.strip()


def build_prompt_text(language=None, depth="deep"):
    """Assemble system prompt from template + language env var. Return string.

    depth: 'deep' (default) or 'shallow'. Selects the prompt template.
    """
    if language is None:
        language = os.environ.get("COLD_REVIEW_LANGUAGE", "\u7e41\u9ad4\u4e2d\u6587\uff08\u53f0\u7063\uff09")
    language = _sanitize_language(language)

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
