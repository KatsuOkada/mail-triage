from __future__ import annotations

from datetime import datetime
from typing import Any

from .mail_datetime import parse_mail_datetime
from .models import MailRecord

GMAIL_MESSAGE_URL = "https://mail.google.com/mail/u/0/#all/{message_id}"
UNCLASSIFIED_CATEGORY = "未分類"
JEV_PENDING = "Jev判断対象"
BASE_GROUPS = ("要確認", "確認不要")


def _source_label(record: MailRecord) -> str:
    """要確認/確認不要の判定根拠(ルール or Jev)を表す短いラベル。Jevの場合は確信度も含める。"""
    if record.verdict_source == "jev":
        confidence = record.jev_confidence or 0.0
        return f"Jev {confidence * 100:.0f}%"
    if record.verdict_source == "rule":
        return "ルール"
    return ""


def _mail_entry(record: MailRecord) -> dict[str, Any]:
    return {
        "message_id": record.message_id,
        "subject": record.subject or "(件名なし)",
        "sender": record.sender,
        "gmail_url": GMAIL_MESSAGE_URL.format(message_id=record.message_id),
        "source_label": _source_label(record),
        # 「要確認」「確認不要」そのもの以外の区分(重要,技術ニュースなど)は、
        # 大項目内で見分けられるようバッジ名として表示する。
        "tier_badge": record.verdict if record.verdict not in (None, *BASE_GROUPS) else None,
    }


def _display_bucket(verdict: str | None, config: dict[str, Any]) -> str:
    if verdict is None:
        return JEV_PENDING
    level = next((lv for lv in config["verdict_levels"] if lv["name"] == verdict), None)
    return level["display_group"] if level is not None else JEV_PENDING


def build_report(records: list[MailRecord], config: dict[str, Any]) -> dict[str, Any]:
    """判定結果を「要確認/確認不要/Jev判断対象 > カテゴリ > メール一覧」に整形する。

    - 重要度区分(config.verdict_levels)のdisplay_groupに従って、要確認/確認不要いずれかに統合表示する
      (どの区分がどちらに属するかはconfigで増減できる)。統合された区分はメール単位のバッジで区別する。
    - 未分類(category未設定)は独立したセクションにはせず、それぞれのverdict配下の
      1カテゴリ(「未分類」)として扱う。
    - Jev判断対象は、config.jev_enabled=falseで段階3がスキップされ、
      verdictが未確定のまま残ったメール(=有効化すればJevに渡っていたメール)。
      通常運用(jev_enabled=true)では空になる。
    - 各カテゴリ内のメールは受信日時の新しい順に並べる。
    """
    sorted_records = sorted(
        records,
        key=lambda r: parse_mail_datetime(r.date) or datetime.min,
        reverse=True,
    )

    sections: dict[str, dict[str, list[dict[str, Any]]]] = {"要確認": {}, "確認不要": {}, JEV_PENDING: {}}
    unclassified_count = 0

    for record in sorted_records:
        category = record.category or UNCLASSIFIED_CATEGORY
        if record.category is None:
            unclassified_count += 1
        bucket = _display_bucket(record.verdict, config)
        sections[bucket].setdefault(category, []).append(_mail_entry(record))

    return {
        "要確認": sections["要確認"],
        "確認不要": sections["確認不要"],
        JEV_PENDING: sections[JEV_PENDING],
        "unclassified_count": unclassified_count,
    }
