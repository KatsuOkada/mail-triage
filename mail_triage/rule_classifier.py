from __future__ import annotations

import re
from typing import Any

from .models import MailRecord


def classify_category(record: MailRecord, config: dict[str, Any]) -> MailRecord:
    """段階1: 送信元ドメインからカテゴリを機械的に確定する。
    一致するルールが無ければ「未分類」(category=None)のまま返す。
    """
    domain = record.sender.rsplit("@", 1)[-1].lower()
    for rule in config["sender_categories"]:
        if re.search(rule["domain_regex"], domain):
            record.category = rule["category"]
            record.category_source = "rule"
            return record

    record.category = None
    record.category_source = "unknown"
    return record


def classify_verdict(record: MailRecord, config: dict[str, Any]) -> MailRecord:
    """段階2: カテゴリ×件名正規表現で要確認/確認不要を確定する。
    複数ルールが競合した場合は安全側(要確認)を優先し、rule_conflictを立てる。
    一致するルールが無ければ確定させず(verdict=None)、段階3(Jev)に委ねる。
    未分類(category=None)のメールは対象外。
    """
    if record.category is None:
        return record

    matched = [
        rule
        for rule in config["importance_rules"]
        if rule["category"] == record.category and re.search(rule["subject_regex"], record.subject)
    ]
    if not matched:
        return record

    verdicts = {rule["verdict"] for rule in matched}
    if len(verdicts) > 1:
        record.verdict = "要確認"
        record.rule_conflict = True
    else:
        record.verdict = verdicts.pop()
        record.rule_conflict = False
    record.verdict_source = "rule"
    return record
