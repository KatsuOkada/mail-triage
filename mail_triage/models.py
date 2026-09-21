from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MailRecord:
    """1件のメールに対する判定パイプラインの入出力。
    各段階を通るたびにフィールドが埋まっていく。
    """

    # 取得(Gmail Fetcher)
    message_id: str
    thread_id: str
    sender: str
    subject: str
    snippet: str
    date: str
    label_ids: list[str] = field(default_factory=list)

    # 段階1: 送信元→カテゴリ
    category: str | None = None
    category_source: str | None = None  # "rule" | "unknown"

    # 段階2: カテゴリ×件名正規表現→要確認/確認不要
    verdict: str | None = None  # "要確認" | "確認不要"
    verdict_source: str | None = None  # "rule" | "jev"
    rule_conflict: bool = False

    # 段階3: Jevによる判定(段階2で未確定だった場合のみ埋まる)
    jev_probability: float | None = None
    jev_confidence: float | None = None
    low_confidence_flag: bool = False

    config_version: int | None = None
