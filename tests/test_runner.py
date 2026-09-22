from mail_triage import runner
from mail_triage.models import MailRecord


def make_config(dry_run: bool) -> dict:
    return {
        "version": 1,
        "dry_run": dry_run,
        "confidence_threshold": 0.3,
        "gmail_fetch": {"base_query": "in:inbox", "initial_lookback_days": 1},
        "sender_categories": [],
        "importance_rules": [],
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
    monkeypatch.setattr(
        runner, "mark_read_and_archive", lambda service, mid, dry_run: calls.append(("archive", dry_run))
    )

    record = make_record(category="EC", verdict="要確認")
    runner.apply_gmail_actions(service=object(), record=record, config=make_config(dry_run=False))

    assert ("label", "EC", False) in calls
    assert not any(c[0] == "archive" for c in calls)  # 要確認は既読化・アーカイブしない


def test_archive_only_when_no_check_needed(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "apply_category_label", lambda *a, **k: calls.append("label"))
    monkeypatch.setattr(runner, "mark_read_and_archive", lambda *a, **k: calls.append("archive"))

    record = make_record(category="EC", verdict="確認不要")
    runner.apply_gmail_actions(service=object(), record=record, config=make_config(dry_run=False))

    assert calls.count("label") == 1
    assert calls.count("archive") == 1


def test_unclassified_mail_gets_no_actions(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "apply_category_label", lambda *a, **k: calls.append("label"))
    monkeypatch.setattr(runner, "mark_read_and_archive", lambda *a, **k: calls.append("archive"))

    record = make_record(category=None, verdict=None)
    runner.apply_gmail_actions(service=object(), record=record, config=make_config(dry_run=False))

    assert calls == []
