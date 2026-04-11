"""Model adapter abstraction — swap CLI / API / mock without changing the engine.

Adapter interface:
    review(diff_text, prompt_text, model) -> (raw_output, exit_code)
    exit_code: 0 = success, -1 = timeout, -2 = not found, other = error
"""

import os
import subprocess
import tempfile


class ModelAdapter:
    """Base class for model adapters."""

    def review(self, diff_text, prompt_text, model):
        """Run a review.  Return (raw_output, exit_code)."""
        raise NotImplementedError


class ClaudeCliAdapter(ModelAdapter):
    """Adapter that invokes the Claude Code CLI."""

    def __init__(self, timeout=300):
        self.timeout = timeout

    def review(self, diff_text, prompt_text, model):
        prompt_fd = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        prompt_fd.write(prompt_text)
        prompt_fd.close()
        try:
            return self._call(diff_text, model, prompt_fd.name)
        finally:
            os.unlink(prompt_fd.name)

    def _call(self, diff_text, model, prompt_file):
        env = {**os.environ, "COLD_REVIEW_ACTIVE": "1"}
        try:
            r = subprocess.run(
                [
                    "claude", "-p", "Review the following changes.",
                    "--model", model,
                    "--append-system-prompt-file", prompt_file,
                    "--output-format", "json",
                ],
                input=diff_text,
                capture_output=True,
                text=True,
                env=env,
                timeout=self.timeout,
            )
            return r.stdout.strip(), r.returncode
        except subprocess.TimeoutExpired:
            return "", -1
        except FileNotFoundError:
            return "", -2


class MockAdapter(ModelAdapter):
    """Adapter that returns a fixed response.  For testing."""

    def __init__(self, response="", exit_code=0):
        self.response = response
        self.exit_code = exit_code
        self.last_diff = None
        self.last_prompt = None
        self.last_model = None
        self.call_count = 0

    def review(self, diff_text, prompt_text, model):
        self.last_diff = diff_text
        self.last_prompt = prompt_text
        self.last_model = model
        self.call_count += 1
        return self.response, self.exit_code


# Backward compat — used nowhere after engine migration, kept for external callers.
def call_claude(diff_text, model, prompt_file):
    """Legacy wrapper.  Prefer ClaudeCliAdapter."""
    adapter = ClaudeCliAdapter()
    with open(prompt_file, "r", encoding="utf-8") as f:
        prompt_text = f.read()
    return adapter.review(diff_text, prompt_text, model)
