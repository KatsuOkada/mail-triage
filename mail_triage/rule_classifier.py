from __future__ import annotations

import re
from typing import Any

from .config_loader import JEV_CHECK
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
    """段階2: カテゴリ×件名正規表現で重要度区分(config.verdict_levels)を確定する。
    importance_rulesは並び順の先勝ち(上に書いた行が優先)。下の行にも別の判定の行が当たっていた場合は
    rule_conflictを立てる(設定の見直し用の目印で、判定は変えない)。
    当たった行の判定が「Jevで確認」の場合と、どの行にも当たらない場合は確定させず(verdict=None)、段階3(Jev)に委ねる。
    「Jevで確認」の場合はjev_check_ruleを立て、段階3でJevに本文を渡す目印にする。
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

    first = matched[0]["verdict"]
    record.rule_conflict = any(rule["verdict"] != first for rule in matched[1:])
    if first == JEV_CHECK:
        record.jev_check_rule = True
        return record
    record.verdict = first
    record.verdict_source = "rule"
    return record
