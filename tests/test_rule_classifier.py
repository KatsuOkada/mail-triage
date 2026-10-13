import json
from pathlib import Path

import pytest

from mail_triage.config_loader import load_config
from mail_triage.models import MailRecord
from mail_triage.rule_classifier import classify_category, classify_verdict

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "classification_rules.example.json"

DEFAULT_VERDICT_LEVELS = [
    {"name": "重要", "display_group": "要確認", "apply_label": True},
    {"name": "要確認", "display_group": "要確認", "apply_label": False},
    {"name": "確認不要", "display_group": "確認不要", "apply_label": False},
]


@pytest.fixture
def config():
    return load_config(CONFIG_PATH)


def make_record(sender: str, subject: str, snippet: str = "") -> MailRecord:
    return MailRecord(
        message_id="m1",
        thread_id="t1",
        sender=sender,
        subject=subject,
        snippet=snippet,
        date="2026-09-22T00:00:00Z",
    )


def test_known_domain_gets_category(config):
    record = make_record("taro@example-corp.co.jp", "【自動通知】システムメンテナンスのお知らせ")
    classify_category(record, config)
    assert record.category == "仕事"
    assert record.category_source == "rule"


def test_subdomain_matches(config):
    record = make_record("no-reply@mail.example-cloud.com", "ご利用状況のお知らせ")
    classify_category(record, config)
    assert record.category == "サービス"


def test_unknown_domain_is_unclassified(config):
    record = make_record("someone@totally-unknown-domain.example", "はじめまして")
    classify_category(record, config)
    assert record.category is None
    assert record.category_source == "unknown"


def test_schedule_notification_is_no_check_needed(config):
    record = make_record("taro@example-corp.co.jp", "【自動通知】システムメンテナンスのお知らせ")
    classify_category(record, config)
    classify_verdict(record, config)
    assert record.verdict == "確認不要"
    assert record.verdict_source == "rule"
    assert record.rule_conflict is False


def test_survey_prefix_is_need_check(config):
    record = make_record("hanako@example-corp.co.jp", "【要回答】社内イベントの出欠確認")
    classify_category(record, config)
    classify_verdict(record, config)
    assert record.verdict == "要確認"


def test_otp_is_no_check_needed(config):
    record = make_record("mail@secure.example-card.jp", "ネットショッピング認証コードのご案内")
    classify_category(record, config)
    assert record.category == "金融"
    classify_verdict(record, config)
    assert record.verdict == "確認不要"


def test_credit_card_billing_is_important(config):
    record = make_record("statement@example-card.jp", "お支払い金額のお知らせ")
    classify_category(record, config)
    assert record.category == "金融"
    classify_verdict(record, config)
    assert record.verdict == "重要"
    assert record.verdict_source == "rule"


def test_no_matching_rule_leaves_verdict_unset(config):
    # 金融カテゴリだが、どの段階2ルールにも一致しない件名 → Jevに委ねるためNoneのまま
    record = make_record("service@example-bank.co.jp", "振込入金のお知らせ")
    classify_category(record, config)
    classify_verdict(record, config)
    assert record.verdict is None


def test_conflicting_rules_prefer_need_check():
    config = {
        "version": 1,
        "dry_run": True,
        "confidence_threshold": 0.3,
        "verdict_levels": DEFAULT_VERDICT_LEVELS,
        "sender_categories": [{"category": "仕事", "domain_regex": "example\\.com$"}],
        "importance_rules": [
            {"category": "仕事", "subject_regex": "テスト", "verdict": "要確認"},
            {"category": "仕事", "subject_regex": "テスト件名", "verdict": "確認不要"},
        ],
    }
    record = make_record("a@example.com", "テスト件名です")
    classify_category(record, config)
    classify_verdict(record, config)
    assert record.verdict == "要確認"
    assert record.rule_conflict is True


def test_conflicting_rules_prefer_important_over_need_check():
    config = {
        "version": 1,
        "dry_run": True,
        "confidence_threshold": 0.3,
        "verdict_levels": DEFAULT_VERDICT_LEVELS,
        "sender_categories": [{"category": "金融", "domain_regex": "example\\.com$"}],
        "importance_rules": [
            {"category": "金融", "subject_regex": "お知らせ", "verdict": "要確認"},
            {"category": "金融", "subject_regex": "お支払い", "verdict": "重要"},
        ],
    }
    record = make_record("a@example.com", "お支払い金額のお知らせ")
    classify_category(record, config)
    classify_verdict(record, config)
    assert record.verdict == "重要"
    assert record.rule_conflict is True


def test_conflict_priority_follows_verdict_levels_order():
    config = {
        "version": 1,
        "dry_run": True,
        "confidence_threshold": 0.3,
        "verdict_levels": [
            {"name": "重要", "display_group": "要確認", "apply_label": True},
            {"name": "技術ニュース", "display_group": "確認不要", "apply_label": True},
            {"name": "要確認", "display_group": "要確認", "apply_label": False},
            {"name": "確認不要", "display_group": "確認不要", "apply_label": False},
        ],
        "sender_categories": [{"category": "技術", "domain_regex": "example\\.com$"}],
        "importance_rules": [
            {"category": "技術", "subject_regex": "リリース", "verdict": "要確認"},
            {"category": "技術", "subject_regex": "新バージョン", "verdict": "技術ニュース"},
        ],
    }
    record = make_record("a@example.com", "新バージョンリリースのお知らせ")
    classify_category(record, config)
    classify_verdict(record, config)
    assert record.verdict == "技術ニュース"
    assert record.rule_conflict is True
