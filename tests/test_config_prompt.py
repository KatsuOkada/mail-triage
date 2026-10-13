from pathlib import Path

from mail_triage.config_prompt import build_config_prompt
from mail_triage.models import MailRecord


def make_record(message_id: str, sender: str) -> MailRecord:
    return MailRecord(
        message_id=message_id,
        thread_id=f"t-{message_id}",
        sender=sender,
        subject="s",
        snippet="",
        date="2026-09-22T00:00:00Z",
    )


def test_prompt_has_no_trailing_newline():
    records = [make_record("m1", "a@example.com")]
    prompt = build_config_prompt(Path("logs/2026-09-22.jsonl"), records)

    # ターミナルに貼り付けた際、末尾の空行にカーソルが残ってEnterが送信されない事態を防ぐ
    assert not prompt.endswith("\n")


def test_prompt_includes_unclassified_count_and_log_path():
    records = [make_record("m1", "a@example.com"), make_record("m2", "b@example.com")]
    prompt = build_config_prompt(Path("logs/2026-09-22.jsonl"), records)

    assert "2件" in prompt
    assert "2026-09-22.jsonl" in prompt


def test_prompt_includes_domain_breakdown():
    records = [
        make_record("m1", "a@example-shop.com"),
        make_record("m2", "b@example-shop.com"),
        make_record("m3", "c@example.com"),
    ]
    prompt = build_config_prompt(Path("logs/2026-09-22.jsonl"), records)

    assert "example-shop.com" in prompt
    assert "example.com" in prompt


def test_prompt_handles_no_unclassified_mail():
    prompt = build_config_prompt(Path("logs/2026-09-22.jsonl"), [])

    assert "0件" in prompt
