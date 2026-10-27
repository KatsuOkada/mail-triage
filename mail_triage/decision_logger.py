from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import date
from pathlib import Path

from .models import MailRecord

_FIELD_NAMES = {f.name for f in fields(MailRecord)}
# 本文は暗証番号・氏名などを含むため、判定ログには書かない
_NOT_LOGGED = {"body"}


def log_path(base_dir: str | Path, for_date: date | None = None) -> Path:
    for_date = for_date or date.today()
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / f"{for_date.isoformat()}.jsonl"


def append_record(record: MailRecord, base_dir: str | Path, for_date: date | None = None) -> None:
    path = log_path(base_dir, for_date)
    row = {k: v for k, v in asdict(record).items() if k not in _NOT_LOGGED}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_records(base_dir: str | Path, for_date: date) -> list[MailRecord]:
    """判定ログを読み込む。スキーマ変更でフィールドが増減しても、
    過去の行(旧フィールドを含む/新フィールドが無い)を読めるよう、未知のキーは無視する。
    """
    path = log_path(base_dir, for_date)
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                raw = json.loads(line)
                known = {k: v for k, v in raw.items() if k in _FIELD_NAMES}
                records.append(MailRecord(**known))
    return records
