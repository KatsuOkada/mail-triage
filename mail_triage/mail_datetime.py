from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime


def parse_mail_datetime(raw_date: str) -> datetime | None:
    """MailRecord.date(GmailのDate:ヘッダそのままの文字列)をローカルのnaive datetimeに変換する。
    パースできない場合はNoneを返す。
    """
    try:
        dt = parsedate_to_datetime(raw_date)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt
