import json

from cold_eyes.intent import intent_prompt_block, load_intent_capsule


def test_missing_hook_input_soft_skips():
    result = load_intent_capsule(None)
    assert result["status"] == "missing_hook_input"
    assert result["summary"] == ""


def test_malformed_hook_input_soft_skips(tmp_path):
    hook = tmp_path / "hook.json"
    hook.write_text("not json", encoding="utf-8")

    result = load_intent_capsule(str(hook))

    assert result["status"] == "malformed_hook_input"


def test_missing_transcript_soft_skips(tmp_path):
    hook = tmp_path / "hook.json"
    hook.write_text(json.dumps({"transcript_path": str(tmp_path / "missing.jsonl")}), encoding="utf-8")

    result = load_intent_capsule(str(hook))

    assert result["status"] == "missing_transcript"


def test_extracts_recent_user_messages_and_ignores_assistant(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join([
            json.dumps({"message": {"role": "user", "content": "請新增自動 gate"}}),
            json.dumps({"message": {"role": "assistant", "content": "我會修改"}}),
            json.dumps({"message": {"role": "user", "content": [{"type": "text", "text": "不要讓我手動記指令"}]}}),
        ]),
        encoding="utf-8",
    )
    hook = tmp_path / "hook.json"
    hook.write_text(json.dumps({"transcript_path": str(transcript)}), encoding="utf-8")

    result = load_intent_capsule(str(hook), max_chars=1200)

    assert result["status"] == "found"
    assert "請新增自動 gate" in result["summary"]
    assert "不要讓我手動記指令" in result["summary"]
    assert "我會修改" not in result["summary"]
    assert result["source"] == "transcript"


def test_capsule_truncates_safely(tmp_path):
    hook = tmp_path / "hook.json"
    hook.write_text(json.dumps({"user_prompt": "a" * 2000}), encoding="utf-8")

    result = load_intent_capsule(str(hook), max_chars=300)

    assert result["status"] == "found"
    assert result["truncated"] is True
    assert len(result["summary"]) == 300


def test_prompt_block_marks_intent_as_low_weight():
    block = intent_prompt_block({"status": "found", "summary": "add login"})

    assert "low weight" in block
    assert "must not override" in block
    assert "diff evidence" in block
