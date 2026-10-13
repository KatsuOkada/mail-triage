from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from .decision_logger import load_records
from .mail_datetime import parse_mail_datetime
from .models import MailRecord
from .rule_classifier import classify_category

DECISION_LOG_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.jsonl$")


def iter_decision_log_records(log_dir: str | Path) -> Iterator[MailRecord]:
    """log_dir配下の判定ログ(YYYY-MM-DD.jsonl、decision_loggerが書き出す日次ファイル)を
    日付順に全て読み込んで返す。report.html/run.logなど他のファイルは対象外。
    """
    log_dir = Path(log_dir)
    for path in sorted(log_dir.glob("*.jsonl")):
        if not DECISION_LOG_FILENAME_RE.match(path.name):
            continue
        for_date = datetime.strptime(path.stem, "%Y-%m-%d").date()
        yield from load_records(log_dir, for_date)


def query_records(
    records: Iterable[MailRecord],
    sender_domain_regex: str | None = None,
    subject_regex: str | None = None,
    snippet_regex: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[MailRecord]:
    """条件に合致するMailRecordを抽出する。指定した条件は全てAND。
    sender_domain_regexは送信元アドレスのドメイン部分(classify_categoryと同じ抽出方法)に対して評価するため、
    config/classification_rules.jsonのdomain_regexと同じ書き方でそのまま件数を試算できる。
    """
    matched = []
    for record in records:
        if sender_domain_regex:
            domain = record.sender.rsplit("@", 1)[-1]
            if not re.search(sender_domain_regex, domain, re.IGNORECASE):
                continue
        if subject_regex and not re.search(subject_regex, record.subject, re.IGNORECASE):
            continue
        if snippet_regex and not re.search(snippet_regex, record.snippet, re.IGNORECASE):
            continue
        if since is not None or until is not None:
            mail_dt = parse_mail_datetime(record.date)
            if mail_dt is None:
                continue
            if since is not None and mail_dt < since:
                continue
            if until is not None and mail_dt > until:
                continue
        matched.append(record)
    return matched


def find_currently_unclassified(log_dir: str | Path, config: dict[str, Any]) -> list[MailRecord]:
    """判定ログ全体(メッセージIDで重複排除)を現在のconfigで再分類し、
    今なおcategoryが確定しないメールだけを返す。

    レポートHTMLに埋め込まれた「未分類件数」は、そのレポートを生成した時点・データ範囲での
    スナップショットに過ぎず、その後のconfig変更や、別の(より狭い範囲の)レポートを見ている場合には
    古い/範囲違いの数値になり得る。正確な現在値が必要な場面ではこちらを使う。
    """
    latest_by_id: dict[str, MailRecord] = {}
    for record in iter_decision_log_records(log_dir):
        latest_by_id[record.message_id] = record

    unclassified = []
    for record in latest_by_id.values():
        record.category = None
        record.category_source = None
        classify_category(record, config)
        if record.category is None:
            unclassified.append(record)
    return unclassified
