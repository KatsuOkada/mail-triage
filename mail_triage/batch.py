from __future__ import annotations

from typing import Any

from googleapiclient.discovery import Resource

from .gmail_client import build_query, get_message_metadata, list_message_ids
from .models import MailRecord


def fetch_inbox_records(service: Resource, config: dict[str, Any]) -> list[MailRecord]:
    """inbox内の対象メールを全件取得する。

    inboxは処理後(手動または一括アーカイブ)に片付けていく運用のため、
    「前回チェック以降の新着分だけ」ではなく、その時点でinboxにある対象を毎回全件取得する。
    """
    query = build_query(config)
    ids = list_message_ids(service, query)
    return [MailRecord(**get_message_metadata(service, message_id)) for message_id in ids]
