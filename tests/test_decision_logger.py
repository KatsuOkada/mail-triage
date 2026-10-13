import json
from datetime import date

from mail_triage.decision_logger import load_records, log_path


def test_load_records_ignores_unknown_legacy_fields(tmp_path):
    for_date = date(2026, 9, 22)
    path = log_path(tmp_path, for_date)
    legacy_row = {
        "message_id": "m1",
        "thread_id": "t1",
        "sender": "a@example.com",
        "subject": "s",
        "snippet": "",
        "date": "2026-09-22T00:00:00Z",
        "jev_probability": 0.5,  # 旧フィールド、現在のMailRecordには存在しない
    }
    path.write_text(json.dumps(legacy_row, ensure_ascii=False) + "\n", encoding="utf-8")

    records = load_records(tmp_path, for_date)

    assert len(records) == 1
    assert records[0].message_id == "m1"
    assert records[0].jev_probabilities is None  # 新フィールドは既定値で埋まる
