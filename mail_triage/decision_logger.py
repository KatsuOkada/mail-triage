from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .models import MailRecord


def log_path(base_dir: str | Path, for_date: date | None = None) -> Path:
    for_date = for_date or date.today()
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / f"{for_date.isoformat()}.jsonl"


def append_record(record: MailRecord, base_dir: str | Path, for_date: date | None = None) -> None:
    path = log_path(base_dir, for_date)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def load_records(base_dir: str | Path, for_date: date) -> list[MailRecord]:
    path = log_path(base_dir, for_date)
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(MailRecord(**json.loads(line)))
    return records
