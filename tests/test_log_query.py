from datetime import date, datetime

from mail_triage.decision_logger import append_record
from mail_triage.log_query import find_currently_unclassified, query_records
from mail_triage.models import MailRecord


def make_record(
    message_id: str,
    sender: str,
    subject: str = "s",
    snippet: str = "",
    date: str = "Tue, 22 Sep 2026 09:00:00 +0900",
) -> MailRecord:
    return MailRecord(
        message_id=message_id,
        thread_id=f"t-{message_id}",
        sender=sender,
        subject=subject,
        snippet=snippet,
        date=date,
    )


def test_filters_by_sender_domain_regex():
    records = [
        make_record("m1", "info@example-shop.com"),
        make_record("m2", "info@example-mall.co.jp"),
    ]

    matched = query_records(records, sender_domain_regex=r"example-shop\.com$")

    assert [r.message_id for r in matched] == ["m1"]


def test_filters_by_subject_regex():
    records = [
        make_record("m1", "a@example.com", subject="セキュリティ通知"),
        make_record("m2", "a@example.com", subject="ご注文の確認"),
    ]

    matched = query_records(records, subject_regex="セキュリティ")

    assert [r.message_id for r in matched] == ["m1"]


def test_filters_by_snippet_regex():
    records = [
        make_record("m1", "a@example.com", snippet="至急ご確認ください"),
        make_record("m2", "a@example.com", snippet="いつもご利用ありがとうございます"),
    ]

    matched = query_records(records, snippet_regex="至急")

    assert [r.message_id for r in matched] == ["m1"]


def test_filters_by_date_range():
    records = [
        make_record("m1", "a@example.com", date="Mon, 14 Sep 2026 09:00:00 +0900"),
        make_record("m2", "a@example.com", date="Tue, 22 Sep 2026 09:00:00 +0900"),
    ]

    matched = query_records(records, since=datetime(2026, 9, 20))

    assert [r.message_id for r in matched] == ["m2"]


def test_combined_filters_are_and():
    records = [
        make_record("m1", "info@example-shop.com", subject="セール開催中"),
        make_record("m2", "info@example-shop.com", subject="ご注文の確認"),
        make_record("m3", "info@example-mall.co.jp", subject="セール開催中"),
    ]

    matched = query_records(records, sender_domain_regex=r"example-shop\.com$", subject_regex="セール")

    assert [r.message_id for r in matched] == ["m1"]


def test_unparseable_date_excluded_when_date_filter_given():
    records = [make_record("m1", "a@example.com", date="not a date")]

    matched = query_records(records, since=datetime(2020, 1, 1))

    assert matched == []


def make_config(sender_categories: list[dict]) -> dict:
    return {"sender_categories": sender_categories}


def test_find_currently_unclassified_reclassifies_with_current_config(tmp_path):
    append_record(make_record("m1", "info@example-shop.com"), tmp_path, date(2026, 9, 20))
    append_record(make_record("m2", "info@unknown-shop.example"), tmp_path, date(2026, 9, 20))

    config = make_config([{"category": "EC", "domain_regex": r"example-shop\.com$"}])

    unclassified = find_currently_unclassified(tmp_path, config)

    assert [r.message_id for r in unclassified] == ["m2"]


def test_find_currently_unclassified_ignores_stale_stored_category(tmp_path):
    # ログに記録された時点ではcategory=EC(古い設定)でも、今の設定に一致しなければ未分類扱いにする
    record = make_record("m1", "info@retired-domain.example")
    record.category = "EC"
    append_record(record, tmp_path, date(2026, 9, 20))

    config = make_config([])  # 現在はどのドメインもEC扱いしない設定に変更されたケース

    unclassified = find_currently_unclassified(tmp_path, config)

    assert [r.message_id for r in unclassified] == ["m1"]


def test_find_currently_unclassified_dedupes_by_message_id(tmp_path):
    append_record(make_record("m1", "info@unknown-shop.example"), tmp_path, date(2026, 9, 20))
    append_record(make_record("m1", "info@unknown-shop.example"), tmp_path, date(2026, 9, 20))

    unclassified = find_currently_unclassified(tmp_path, make_config([]))

    assert len(unclassified) == 1
