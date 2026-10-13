from __future__ import annotations

from typing import Any

from googleapiclient.discovery import Resource

from .decision_logger import append_record
from .gmail_client import apply_category_label, apply_label
from .jev_adapter import classify_verdict_by_jev
from .models import MailRecord
from .rule_classifier import classify_category, classify_verdict


def _verdict_level(config: dict[str, Any], verdict: str | None) -> dict[str, Any] | None:
    return next((level for level in config["verdict_levels"] if level["name"] == verdict), None)


def process_record(record: MailRecord, config: dict[str, Any]) -> MailRecord:
    """1件のメールを段階1→2→3の順で処理する。
    config.jev_enabledがfalseの場合、段階3(Jev)はスキップし、
    段階1,2で確定しなかったメールはverdict未確定(Jev判断対象)のまま残す。
    """
    classify_category(record, config)
    classify_verdict(record, config)
    if config["jev_enabled"]:
        classify_verdict_by_jev(record, config)
    record.config_version = config["version"]
    return record


def apply_gmail_actions(service: Resource, record: MailRecord, config: dict[str, Any]) -> None:
    """判定結果をGmailに書き戻す。dry_run中は各関数が内部で何もしない。

    - 分類済み(category確定)なら、対応するラベルを付与する
    - 重要度区分(config.verdict_levels)ごとのapply_label設定に従い、ラベルを付与する
    既読化・アーカイブ(inboxから消す操作)はここでは行わない。レポート画面の
    「一括既読・アーカイブ」ボタンで意図的に実行したときだけ行う(自動で消えると再確認しづらいため)。
    """
    dry_run = config["dry_run"]

    if record.category is not None:
        apply_category_label(service, record.message_id, record.category, dry_run)

    level = _verdict_level(config, record.verdict)
    if level is None:
        return

    if level["apply_label"]:
        # Gmailは"重要"などシステムラベルの表示名と衝突する名前でのラベル作成を拒否するため、
        # 区分名(name)と実際に付与するラベル名(label_name)を分けられるようにしてある。
        label_name = level.get("label_name", level["name"])
        apply_label(service, record.message_id, label_name, dry_run)


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
