from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import Resource

from .fetch_state import load_last_checked
from .gmail_client import build_query, get_message_metadata, list_message_ids
from .models import MailRecord


def fetch_new_records(service: Resource, config: dict[str, Any]) -> tuple[list[MailRecord], datetime]:
    """前回チェック時刻以降の新着メールを取得する。

    run_startは実行「開始」時点の時刻。取得・判定・書き戻しの処理中に
    新たなメールが届いても、次回はrun_start以降として再度拾われるため
    取りこぼしが起きない(「終了」時刻を基準にすると、処理中に届いたメールを
    永久に取りこぼす可能性がある)。呼び出し側は、全処理が成功した後に
    fetch_state.save_last_checked(run_start)を呼ぶこと。
    """
    run_start = datetime.now(timezone.utc)
    last_checked = load_last_checked()
    query = build_query(config, last_checked)

    ids = list_message_ids(service, query)
    records = [MailRecord(**get_message_metadata(service, message_id)) for message_id in ids]
    return records, run_start
