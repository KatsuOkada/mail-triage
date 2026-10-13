import json
from datetime import datetime
from unittest import mock

import pytest

from mail_triage.dashboard_export import build_dashboard_summary, export_dashboard_summary
from mail_triage.models import MailRecord

DEFAULT_CONFIG = {
    "verdict_levels": [
        {"name": "重要", "display_group": "要確認", "apply_label": True},
        {"name": "技術ニュース", "display_group": "確認不要", "apply_label": True},
        {"name": "要確認", "display_group": "要確認", "apply_label": False},
        {"name": "確認不要", "display_group": "確認不要", "apply_label": False},
    ]
}
NOW = datetime(2026, 10, 11, 1, 0, 7)


def make_record(
    message_id: str,
    verdict: str | None,
    date: str = "Fri, 9 Oct 2026 15:18:34 +0000",
    sender: str = "Shop <shop@example.com>",
    subject: str = "s",
) -> MailRecord:
    return MailRecord(
        message_id=message_id,
        thread_id=f"t-{message_id}",
        sender=sender,
        subject=subject,
        snippet="",
        date=date,
        verdict=verdict,
    )


def test_counts_every_verdict_level_and_total():
    records = [
        make_record("m1", "重要"),
        make_record("m2", "確認不要"),
        make_record("m3", "確認不要"),
        make_record("m4", None),  # Jev判断待ち
    ]
    summary = build_dashboard_summary(records, DEFAULT_CONFIG, NOW)
    assert summary["total"] == 4
    assert summary["counts"] == {"重要": 1, "技術ニュース": 0, "要確認": 0, "確認不要": 2}
    assert summary["generated_at"] == "2026-10-11T01:00:07"


def test_attention_lists_only_attention_group_ordered_by_level_then_newest():
    records = [
        make_record("old-check", "要確認", date="Thu, 8 Oct 2026 10:00:00 +0900", subject="古い要確認"),
        make_record("news", "技術ニュース"),
        make_record("new-check", "要確認", date="Sat, 10 Oct 2026 10:00:00 +0900", subject="新しい要確認"),
        make_record("important", "重要", date="Wed, 7 Oct 2026 10:00:00 +0900", subject="重要"),
    ]
    summary = build_dashboard_summary(records, DEFAULT_CONFIG, NOW)
    assert [a["subject"] for a in summary["attention"]] == ["重要", "新しい要確認", "古い要確認"]


def test_attention_has_no_sender_and_placeholder_subject():
    records = [
        make_record("m1", "重要", sender="Shop <shop@example.com>"),
        make_record("m2", "重要", sender="plain@example.com", subject=""),
    ]
    attention = build_dashboard_summary(records, DEFAULT_CONFIG, NOW)["attention"]
    assert all("sender" not in a for a in attention)  # 画面に出さない情報は送らない
    assert attention[1]["subject"] == "(件名なし)"


def test_export_writes_json_and_skips_push_without_target(tmp_path):
    with mock.patch("mail_triage.dashboard_export.subprocess.run") as run:
        path = export_dashboard_summary([make_record("m1", "重要")], DEFAULT_CONFIG, tmp_path, NOW)
    assert json.loads(path.read_text(encoding="utf-8"))["counts"]["重要"] == 1
    run.assert_not_called()


def test_export_pushes_summary_over_ssh_stdin_when_host_configured(tmp_path):
    config = {**DEFAULT_CONFIG, "dashboard_push_host": "dashboard-host"}
    with mock.patch("mail_triage.dashboard_export.subprocess.run") as run:
        path = export_dashboard_summary([], config, tmp_path, NOW)
    args = run.call_args.args[0]
    assert args[0] == "ssh"
    assert args[-2:] == ["--", "dashboard-host"]
    assert run.call_args.kwargs["input"] == path.read_bytes()


@pytest.mark.parametrize("host", ["-oProxyCommand=calc", "dashboard host", "user@host;rm"])
def test_export_rejects_host_that_could_be_an_ssh_option(tmp_path, host):
    config = {**DEFAULT_CONFIG, "dashboard_push_host": host}
    with mock.patch("mail_triage.dashboard_export.subprocess.run") as run, pytest.raises(ValueError):
        export_dashboard_summary([], config, tmp_path, NOW)
    run.assert_not_called()
