import json
from pathlib import Path

import pytest

from mail_triage.config_loader import load_config
from mail_triage.models import MailRecord
from mail_triage.rule_classifier import classify_category, classify_verdict

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "classification_rules.json"


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
    record = make_record("k-okada@bell-c.co.jp", "09月18日 岡田 勝志郎さんのスケジュール")
    classify_category(record, config)
    assert record.category == "仕事"
    assert record.category_source == "rule"


def test_subdomain_matches(config):
    record = make_record("miruden@a2.kepco.co.jp", "かんでん保険のご案内")
    classify_category(record, config)
    assert record.category == "EC"


def test_unknown_domain_is_unclassified(config):
    record = make_record("someone@totally-unknown-domain.example", "はじめまして")
    classify_category(record, config)
    assert record.category is None
    assert record.category_source == "unknown"


def test_schedule_notification_is_no_check_needed(config):
    record = make_record("k-okada@bell-c.co.jp", "09月18日 岡田 勝志郎さんのスケジュール")
    classify_category(record, config)
    classify_verdict(record, config)
    assert record.verdict == "確認不要"
    assert record.verdict_source == "rule"
    assert record.rule_conflict is False


def test_survey_prefix_is_no_check_needed(config):
    record = make_record("m-honda@bell-c.co.jp", "アンケート：【社員会】忘年会（大阪）　出欠確認アンケート")
    classify_category(record, config)
    classify_verdict(record, config)
    assert record.verdict == "確認不要"


def test_otp_is_no_check_needed(config):
    record = make_record("mail@pc3.jp-bank-card.jp", "ネットショッピング認証コードのご案内")
    classify_category(record, config)
    assert record.category == "金融"
    classify_verdict(record, config)
    assert record.verdict == "確認不要"


def test_no_matching_rule_leaves_verdict_unset(config):
    # 金融カテゴリだが、どの段階2ルールにも一致しない件名 → Jevに委ねるためNoneのまま
    record = make_record("SMBC_service@dn.smbc.co.jp", "【三井住友銀行】振込入金のお知らせ")
    classify_category(record, config)
    classify_verdict(record, config)
    assert record.verdict is None


def test_conflicting_rules_prefer_need_check():
    config = {
        "version": 1,
        "dry_run": True,
        "confidence_threshold": 0.3,
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
