from __future__ import annotations

from typing import Any

from .decision_logger import append_record
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


def run(records: list[MailRecord], config: dict[str, Any], log_dir: str) -> list[MailRecord]:
    """複数件のメールを処理し、日次JSONLに記録する。"""
    processed = []
    for record in records:
        process_record(record, config)
        append_record(record, log_dir)
        processed.append(record)
    return processed
