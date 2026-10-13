from mail_triage.models import MailRecord
from mail_triage.report_builder import build_report

DEFAULT_CONFIG = {
    "verdict_levels": [
        {"name": "重要", "display_group": "要確認", "apply_label": True},
        {"name": "技術ニュース", "display_group": "確認不要", "apply_label": True},
        {"name": "要確認", "display_group": "要確認", "apply_label": False},
        {"name": "確認不要", "display_group": "確認不要", "apply_label": False},
    ]
}


def make_record(
    message_id: str,
    category: str | None,
    verdict: str | None,
    subject: str = "s",
    verdict_source: str | None = None,
    jev_confidence: float | None = None,
    date: str = "2026-09-22T00:00:00Z",
) -> MailRecord:
    return MailRecord(
        message_id=message_id,
        thread_id=f"t-{message_id}",
        sender="a@example.com",
        subject=subject,
        snippet="",
        date=date,
        category=category,
        verdict=verdict,
        verdict_source=verdict_source,
        jev_confidence=jev_confidence,
    )


def test_groups_by_verdict_then_category():
    records = [
        make_record("m1", "EC", "確認不要"),
        make_record("m2", "EC", "要確認"),
        make_record("m3", "仕事", "要確認"),
    ]

    report = build_report(records, DEFAULT_CONFIG)

    assert [e["message_id"] for e in report["確認不要"]["EC"]] == ["m1"]
    assert [e["message_id"] for e in report["要確認"]["EC"]] == ["m2"]
    assert [e["message_id"] for e in report["要確認"]["仕事"]] == ["m3"]
    assert report["unclassified_count"] == 0


def test_unclassified_mail_is_a_category_under_its_verdict():
    records = [
        make_record("m1", None, "要確認"),
        make_record("m2", None, "確認不要"),
    ]

    report = build_report(records, DEFAULT_CONFIG)

    assert [e["message_id"] for e in report["要確認"]["未分類"]] == ["m1"]
    assert [e["message_id"] for e in report["確認不要"]["未分類"]] == ["m2"]
    assert report["unclassified_count"] == 2


def test_gmail_url_uses_message_id():
    report = build_report([make_record("abc123", "EC", "確認不要")], DEFAULT_CONFIG)

    entry = report["確認不要"]["EC"][0]
    assert entry["gmail_url"] == "https://mail.google.com/mail/u/0/#all/abc123"


def test_source_label_for_rule():
    report = build_report([make_record("m1", "EC", "確認不要", verdict_source="rule")], DEFAULT_CONFIG)

    assert report["確認不要"]["EC"][0]["source_label"] == "ルール"


def test_source_label_for_jev_includes_confidence():
    report = build_report(
        [make_record("m1", "EC", "要確認", verdict_source="jev", jev_confidence=0.66)], DEFAULT_CONFIG
    )

    assert report["要確認"]["EC"][0]["source_label"] == "Jev 66%"


def test_important_is_shown_under_need_check_bucket_with_badge():
    records = [
        make_record("m1", "金融", "重要"),
        make_record("m2", "金融", "要確認"),
    ]

    report = build_report(records, DEFAULT_CONFIG)

    entries = {e["message_id"]: e for e in report["要確認"]["金融"]}
    assert entries["m1"]["tier_badge"] == "重要"
    assert entries["m2"]["tier_badge"] is None
    assert report["確認不要"] == {}


def test_tech_news_is_shown_under_no_check_bucket_with_badge():
    records = [make_record("m1", "技術", "技術ニュース")]

    report = build_report(records, DEFAULT_CONFIG)

    entry = report["確認不要"]["技術"][0]
    assert entry["tier_badge"] == "技術ニュース"
    assert report["要確認"] == {}


def test_sorted_by_received_date_descending():
    records = [
        make_record("old", "EC", "確認不要", date="Mon, 14 Sep 2026 09:00:00 +0900"),
        make_record("new", "EC", "確認不要", date="Tue, 22 Sep 2026 09:00:00 +0900"),
        make_record("mid", "EC", "確認不要", date="Fri, 18 Sep 2026 09:00:00 +0900"),
    ]

    report = build_report(records, DEFAULT_CONFIG)

    assert [e["message_id"] for e in report["確認不要"]["EC"]] == ["new", "mid", "old"]


def test_unresolved_verdict_goes_to_jev_pending():
    records = [
        make_record("m1", "EC", None),
        make_record("m2", None, None),
    ]

    report = build_report(records, DEFAULT_CONFIG)

    assert [e["message_id"] for e in report["Jev判断対象"]["EC"]] == ["m1"]
    assert [e["message_id"] for e in report["Jev判断対象"]["未分類"]] == ["m2"]
    assert report["要確認"] == {}
    assert report["確認不要"] == {}
    assert report["unclassified_count"] == 1
