from unittest.mock import MagicMock

from mail_triage import runner
from mail_triage.models import MailRecord


def make_config(dry_run: bool, jev_enabled: bool = True) -> dict:
    return {
        "version": 1,
        "dry_run": dry_run,
        "confidence_threshold": 0.3,
        "jev_enabled": jev_enabled,
        "gmail_fetch": {"base_query": "in:inbox"},
        "sender_categories": [],
        "importance_rules": [],
        "verdict_levels": [
            {"name": "重要", "display_group": "要確認", "apply_label": True},
            {"name": "技術ニュース", "display_group": "確認不要", "apply_label": True},
            {"name": "要確認", "display_group": "要確認", "apply_label": False},
            {"name": "確認不要", "display_group": "確認不要", "apply_label": False},
        ],
    }


def make_record(category: str | None, verdict: str | None) -> MailRecord:
    return MailRecord(
        message_id="m1",
        thread_id="t1",
        sender="a@example.com",
        subject="s",
        snippet="",
        date="2026-09-22T00:00:00Z",
        category=category,
        verdict=verdict,
    )


def test_labels_applied_when_category_known(monkeypatch):
    calls = []
    monkeypatch.setattr(
        runner, "apply_category_label", lambda service, mid, category, dry_run: calls.append(("label", category, dry_run))
    )

    record = make_record(category="EC", verdict="要確認")
    runner.apply_gmail_actions(service=object(), record=record, config=make_config(dry_run=False))

    assert calls == [("label", "EC", False)]


def test_never_archives_automatically_even_when_no_check_needed(monkeypatch):
    # inboxから消す操作は、レポート画面の一括ボタンで意図的に行ったときだけ。
    for verdict, category in [("確認不要", "EC"), ("技術ニュース", "技術")]:
        monkeypatch.setattr(runner, "apply_category_label", lambda *a, **k: None)
        monkeypatch.setattr(runner, "apply_label", lambda *a, **k: None)
        service = MagicMock()

        record = make_record(category=category, verdict=verdict)
        runner.apply_gmail_actions(service=service, record=record, config=make_config(dry_run=False))

        assert service.mock_calls == []


def test_important_gets_category_and_tier_label(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "apply_category_label", lambda *a, **k: calls.append("category_label"))
    monkeypatch.setattr(runner, "apply_label", lambda service, mid, label, dry_run: calls.append(("tier_label", label)))

    record = make_record(category="金融", verdict="重要")
    runner.apply_gmail_actions(service=object(), record=record, config=make_config(dry_run=False))

    assert calls == ["category_label", ("tier_label", "重要")]


def test_label_name_override_is_used_instead_of_verdict_name(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "apply_category_label", lambda *a, **k: None)
    monkeypatch.setattr(runner, "apply_label", lambda service, mid, label, dry_run: calls.append(label))

    config = make_config(dry_run=False)
    # Gmailが"重要"という名前のラベル作成を拒否するため、label_nameで別名に上書きするケース
    config["verdict_levels"][0]["label_name"] = "重要メール"

    record = make_record(category="金融", verdict="重要")
    runner.apply_gmail_actions(service=object(), record=record, config=config)

    assert calls == ["重要メール"]


def test_tech_news_gets_tier_label(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "apply_category_label", lambda *a, **k: calls.append("category_label"))
    monkeypatch.setattr(runner, "apply_label", lambda service, mid, label, dry_run: calls.append(("tier_label", label)))

    record = make_record(category="技術", verdict="技術ニュース")
    runner.apply_gmail_actions(service=object(), record=record, config=make_config(dry_run=False))

    assert ("tier_label", "技術ニュース") in calls


def test_unclassified_mail_gets_no_actions(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "apply_category_label", lambda *a, **k: calls.append("label"))

    record = make_record(category=None, verdict=None)
    runner.apply_gmail_actions(service=object(), record=record, config=make_config(dry_run=False))

    assert calls == []


def test_jev_disabled_leaves_verdict_unresolved(monkeypatch):
    monkeypatch.setattr(runner, "classify_verdict_by_jev", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("jev_enabled=Falseの場合はJevを呼び出してはいけない")
    ))

    record = make_record(category="EC", verdict=None)
    result = runner.process_record(record, make_config(dry_run=True, jev_enabled=False))

    assert result.verdict is None
    assert result.config_version == 1


def test_jev_enabled_still_calls_jev_when_unresolved(monkeypatch):
    calls = []
    monkeypatch.setattr(
        runner,
        "classify_verdict_by_jev",
        lambda record, config: calls.append(record.message_id) or record,
    )

    record = make_record(category="仕事", verdict=None)
    runner.process_record(record, make_config(dry_run=True, jev_enabled=True))

    assert calls == ["m1"]
