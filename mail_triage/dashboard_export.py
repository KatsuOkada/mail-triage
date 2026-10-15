"""外部のダッシュボード用ホストに渡す、判定結果の要約を作って送る。

要約は logs/dashboard_summary.json に書き出し、config の dashboard_push_host
(~/.ssh/config の Host 名。例: "dashboard-host")が設定されていれば、ssh の標準入力で送る。
送り先のホストでは、この送信専用の鍵に authorized_keys の command= で
「標準入力を data/mail_triage.json に保存するだけ」の処理を割り当てておく
(鍵が漏れても送り先で他の操作はできない)。画面に出さない送信者名は送らない。
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from .mail_datetime import parse_mail_datetime
from .models import MailRecord

logger = logging.getLogger("mail_triage")

SUMMARY_FILENAME = "dashboard_summary.json"
ATTENTION_GROUP = "要確認"
MAX_ATTENTION_ITEMS = 20
HOST_ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def build_dashboard_summary(
    records: list[MailRecord], config: dict[str, Any], generated_at: datetime
) -> dict[str, Any]:
    """受信トレイ全体の判定別件数と、display_group が「要確認」のメール一覧(新しい順)を返す。"""
    levels = config["verdict_levels"]
    attention_verdicts = {level["name"] for level in levels if level["display_group"] == ATTENTION_GROUP}
    order = {level["name"]: i for i, level in enumerate(levels)}

    attention = [r for r in records if r.verdict in attention_verdicts]
    attention.sort(key=lambda r: parse_mail_datetime(r.date) or datetime.min, reverse=True)
    attention.sort(key=lambda r: order[r.verdict])  # 安定ソートなので、判定の重さ順 → 新しい順

    return {
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "total": len(records),
        "counts": {level["name"]: sum(1 for r in records if r.verdict == level["name"]) for level in levels},
        "attention": [
            {
                "verdict": r.verdict,
                "subject": r.subject or "(件名なし)",
            }
            for r in attention[:MAX_ATTENTION_ITEMS]
        ],
    }


def export_dashboard_summary(
    records: list[MailRecord], config: dict[str, Any], log_dir: Path, generated_at: datetime
) -> Path:
    path = log_dir / SUMMARY_FILENAME
    summary = build_dashboard_summary(records, config, generated_at)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # ダッシュボードと同じ機械で動かすときは、ssh で送らずにファイルを置くだけでよい
    local_copy = os.environ.get("MAIL_TRIAGE_DASHBOARD_COPY")
    if local_copy:
        shutil.copyfile(path, local_copy)
        logger.info("ダッシュボード用の要約を置きました: %s", local_copy)

    host = config.get("dashboard_push_host")
    if host:
        # ssh のオプションとして解釈される値(-oProxyCommand=... など)を渡さないよう、Host 名の形だけ許す
        if not HOST_ALIAS_PATTERN.match(host):
            raise ValueError(f"dashboard_push_host の形式が不正です: {host!r}")
        subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "--", host],
            input=path.read_bytes(), check=True, capture_output=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # pythonw.exe から呼ばれても窓を出さない
        )
        logger.info("ダッシュボード用の要約を送りました: %s", host)
    return path
