from __future__ import annotations

from typing import Any

from googleapiclient.discovery import Resource

from .decision_logger import append_record
from .gmail_client import apply_category_label, mark_read_and_archive
from .jev_adapter import classify_verdict_by_jev
from .models import MailRecord
from .rule_classifier import classify_category, classify_verdict


def process_record(record: MailRecord, config: dict[str, Any]) -> MailRecord:
    """1件のメールを段階1→2→3の順で処理する。"""
    classify_category(record, config)
    classify_verdict(record, config)
    classify_verdict_by_jev(record, config)
    record.config_version = config["version"]
    return record


def apply_gmail_actions(service: Resource, record: MailRecord, config: dict[str, Any]) -> None:
    """判定結果をGmailに書き戻す。dry_run中は各関数が内部で何もしない。

    - 分類済み(category確定)なら、対応するラベルを付与する
    - 確認不要なら、既読化・アーカイブする(要確認は対象外、手動対応)
    """
    dry_run = config["dry_run"]

    if record.category is not None:
        apply_category_label(service, record.message_id, record.category, dry_run)

    if record.verdict == "確認不要":
        mark_read_and_archive(service, record.message_id, dry_run)


def run(
    records: list[MailRecord],
    config: dict[str, Any],
    log_dir: str,
    service: Resource | None = None,
) -> list[MailRecord]:
    """複数件のメールを処理し、日次JSONLに記録する。
    serviceを渡した場合のみ、Gmailへの書き戻し(ラベル付与・既読化/アーカイブ)も行う。
    """
    processed = []
    for record in records:
        process_record(record, config)
        if service is not None:
            apply_gmail_actions(service, record, config)
        append_record(record, log_dir)
        processed.append(record)
    return processed
