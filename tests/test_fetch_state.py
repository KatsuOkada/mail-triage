from datetime import datetime, timezone

from mail_triage.fetch_state import load_last_checked, save_last_checked
from mail_triage.gmail_client import build_query


def test_no_state_file_returns_none(tmp_path):
    assert load_last_checked(tmp_path / "does_not_exist.json") is None


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    when = datetime(2026, 9, 22, 7, 0, 0, tzinfo=timezone.utc)
    save_last_checked(when, path)
    loaded = load_last_checked(path)
    assert loaded == when


def test_build_query_first_run_uses_lookback():
    config = {"gmail_fetch": {"base_query": "in:inbox", "initial_lookback_days": 2}}
    query = build_query(config, None)
    assert query == "in:inbox newer_than:2d"


def test_build_query_subsequent_run_uses_after_epoch():
    config = {"gmail_fetch": {"base_query": "in:inbox"}}
    when = datetime(2026, 9, 22, 7, 0, 0, tzinfo=timezone.utc)
    query = build_query(config, when)
    assert query == f"in:inbox after:{int(when.timestamp())}"
