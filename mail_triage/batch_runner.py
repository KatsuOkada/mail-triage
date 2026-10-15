from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

from googleapiclient.discovery import Resource

from .batch import fetch_inbox_records
from .config_loader import load_config
from .dashboard_export import export_dashboard_summary
from .html_report import render_html
from .logging_setup import setup_logging
from .report_builder import build_report
from .runner import run

logger = logging.getLogger("mail_triage")


def run_once(
    service: Resource,
    config_path: str | Path,
    log_dir: str | Path,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """inbox内の対象メールを全件処理し、レビュー用レポートを書き出す。

    scripts/run_batch.py(CLIからの実行)と、トレイアプリの「手動実行」の両方から
    共通のロジックとして呼ばれる。戻り値は書き出したレポートファイルのパス。
    progress を渡すと、段階が変わるたびに段階名(画面表示用)で呼ばれる。
    """
    report = progress or (lambda stage: None)
    log_dir = Path(log_dir)
    now = datetime.now()
    setup_logging(log_dir, now)
    try:
        config = load_config(config_path)

        report("メールの取得")
        records = fetch_inbox_records(service, config)
        logger.info(
            "inbox内%d件を処理します(dry_run=%s, jev_enabled=%s)。",
            len(records), config["dry_run"], config["jev_enabled"],
        )

        report("分類とGmailへの反映")
        processed = run(records, config, log_dir, service=service)

        verdict_names = [level["name"] for level in config["verdict_levels"]]
        counts = {name: sum(1 for r in processed if r.verdict == name) for name in verdict_names}
        unclassified = sum(1 for r in processed if r.category is None)
        low_conf = sum(1 for r in processed if r.low_confidence_flag)
        jev_pending = sum(1 for r in processed if r.verdict not in verdict_names)

        summary = " / ".join(f"{name}: {count}件" for name, count in counts.items())
        logger.info(
            "%s / 未分類: %d件 / 低確信度: %d件 / Jev判断対象: %d件",
            summary, unclassified, low_conf, jev_pending,
        )

        report("レポートの作成")
        report_data = build_report(processed, config)
        report_html = render_html(report_data, now.strftime("%Y-%m-%d %H:%M:%S"))
        report_path = log_dir / f"{now.strftime('%Y-%m-%d_%H%M%S')}_report.html"
        report_path.write_text(report_html, encoding="utf-8")
        logger.info("レポートを書き出しました: %s", report_path)

        # ダッシュボードは補助的な表示なので、送れなくてもバッチ自体は成功扱いにする
        try:
            export_dashboard_summary(processed, config, log_dir, now)
        except Exception:
            logger.warning("ダッシュボード用の要約を出力・送信できませんでした。", exc_info=True)
        return report_path
    except Exception:
        logger.exception("バッチ実行中にエラーが発生しました。")
        raise
