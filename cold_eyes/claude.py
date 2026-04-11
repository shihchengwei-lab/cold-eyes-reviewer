"""Claude CLI invocation."""

import os
import subprocess


def call_claude(diff_text, model, prompt_file):
    """Call claude CLI. Return (raw_stdout, exit_code)."""
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
            timeout=300,
        )
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", -1
    except FileNotFoundError:
        return "", -2
