"""段階3(Jev)に本文を渡す処理のテスト。
本文を渡すのは「Jevで確認」の行に当たったメールだけで、
どの行にも当たらなかったメール・未分類のメールは今まで通り件名とsnippetで判定する。
"""
import json
import re
from datetime import date

import pytest

from mail_triage import runner
from mail_triage.config_loader import _validate
from mail_triage.decision_logger import append_record, load_records, log_path
from mail_triage.jev_adapter import _build_payload
from mail_triage.models import MailRecord

VERDICT_LEVELS = [
    {"name": "要確認", "display_group": "要確認", "apply_label": False},
    {"name": "確認不要", "display_group": "確認不要", "apply_label": False},
]


def make_config(**overrides) -> dict:
    config = {
        "version": 1,
        "dry_run": True,
        "jev_enabled": True,
        "confidence_threshold": 0.3,
        "gmail_fetch": {"base_query": "in:inbox"},
        "sender_categories": [{"category": "EC", "domain_regex": "(^|\\.)shop\\.example$"}],
        "importance_rules": [
            {"category": "EC", "subject_regex": "^配達済み", "verdict": "Jevで確認"},
            {"category": "EC", "subject_regex": ".*", "verdict": "確認不要"},
        ],
        "jev_prompt": {"instructions": "i", "criteria": {"要確認": "a", "確認不要": "b"}},
        "verdict_levels": VERDICT_LEVELS,
    }
    config.update(overrides)
    return config


def make_record(sender: str, subject: str) -> MailRecord:
    return MailRecord(
        message_id="m1", thread_id="t1", sender=sender, subject=subject, snippet="件名だけのsnippet", date="d"
    )


@pytest.fixture
def fake_pipeline(monkeypatch):
    """本文の取得とJevの呼び出しを差し替え、呼ばれ方を記録する。"""
    calls = {"body": [], "jev": []}

    def fake_body(service, message_id, max_chars, redact_regexes):
        calls["body"].append((message_id, max_chars, redact_regexes))
        return "ロッカー番号：1、暗証番号：0000"

    def fake_jev(record, config):
        if record.verdict is None:
            calls["jev"].append(record.body)
            record.verdict = "要確認"
            record.verdict_source = "jev"
        return record

    monkeypatch.setattr(runner, "get_message_body", fake_body)
    monkeypatch.setattr(runner, "classify_verdict_by_jev", fake_jev)
    return calls


def test_jev_check_rule_fetches_body_and_goes_to_jev(fake_pipeline):
    record = make_record("order-update@shop.example", "配達済み: 「サンプル商品」")
    runner.process_record(record, make_config(), service=object())
    assert fake_pipeline["body"] == [("m1", 500, [])]
    assert fake_pipeline["jev"] == ["ロッカー番号：1、暗証番号：0000"]
    assert record.jev_check_rule is True
    assert record.verdict == "要確認"
    assert record.verdict_source == "jev"


def test_unclassified_mail_goes_to_jev_without_body(fake_pipeline):
    # 未分類のメールは、本文を取らずに件名とsnippetでJevが判定する
    record = make_record("someone@unknown.example", "はじめまして")
    runner.process_record(record, make_config(), service=object())
    assert fake_pipeline["body"] == []
    assert fake_pipeline["jev"] == [None]


def test_mail_matching_no_rule_goes_to_jev_without_body(fake_pipeline):
    # カテゴリは決まったが、どの行にも当たらないメールも本文は取らない
    config = make_config(importance_rules=[{"category": "EC", "subject_regex": "^配達済み", "verdict": "Jevで確認"}])
    record = make_record("ship@shop.example", "発送しました")
    runner.process_record(record, config, service=object())
    assert fake_pipeline["body"] == []
    assert fake_pipeline["jev"] == [None]
    assert record.jev_check_rule is False


def test_rule_decided_mail_does_not_fetch_body(fake_pipeline):
    record = make_record("ship@shop.example", "発送しました")
    runner.process_record(record, make_config(), service=object())
    assert fake_pipeline["body"] == []
    assert fake_pipeline["jev"] == []
    assert record.verdict == "確認不要"


def test_body_not_fetched_when_jev_disabled(fake_pipeline):
    record = make_record("order-update@shop.example", "配達済み: 「サンプル商品」")
    runner.process_record(record, make_config(jev_enabled=False), service=object())
    assert fake_pipeline["body"] == []
    assert record.verdict is None


def test_body_settings_come_from_config(fake_pipeline):
    config = make_config(jev_body={"max_chars": 300, "redact_regexes": ["山田"]})
    runner.process_record(make_record("a@shop.example", "配達済み: x"), config, service=object())
    assert fake_pipeline["body"] == [("m1", 300, ["山田"])]


def test_without_service_jev_gets_snippet(fake_pipeline):
    record = make_record("a@shop.example", "配達済み: x")
    runner.process_record(record, make_config())
    assert fake_pipeline["body"] == []
    assert fake_pipeline["jev"] == [None]


def test_jev_payload_uses_body_when_present():
    record = make_record("a@shop.example", "配達済み")
    record.body = "ロッカー番号：1、暗証番号：0000"
    assert _build_payload(record, make_config())["state"].endswith("本文: ロッカー番号：1、暗証番号：0000")


def test_jev_payload_falls_back_to_snippet():
    record = make_record("a@shop.example", "配達済み")
    assert _build_payload(record, make_config())["state"].endswith("本文: 件名だけのsnippet")


def test_body_is_not_written_to_decision_log(tmp_path):
    # 本文(暗証番号・氏名など)は判定ログに残さない
    record = make_record("a@shop.example", "配達済み")
    record.body = "暗証番号：0000"
    append_record(record, tmp_path, date(2026, 10, 27))
    raw = json.loads(log_path(tmp_path, date(2026, 10, 27)).read_text(encoding="utf-8"))
    assert "body" not in raw
    assert load_records(tmp_path, date(2026, 10, 27))[0].body is None


def test_config_accepts_jev_check_verdict():
    _validate(make_config())


def test_config_rejects_unknown_verdict():
    config = make_config(importance_rules=[{"category": "EC", "subject_regex": ".*", "verdict": "Jevで"}])
    with pytest.raises(ValueError):
        _validate(config)


@pytest.mark.parametrize(
    "jev_body",
    [{"max_chars": 0}, {"max_chars": "100"}, {"redact_regexes": ["("]}, {"redact_regexes": "山田"}],
)
def test_config_rejects_invalid_jev_body(jev_body):
    with pytest.raises((ValueError, re.error)):
        _validate(make_config(jev_body=jev_body))
