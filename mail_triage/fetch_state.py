from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_PATH = ROOT / "config" / "fetch_state.json"


def load_last_checked(path: str | Path = DEFAULT_STATE_PATH) -> datetime | None:
    """前回の実行開始時刻を返す。状態ファイルが無ければNone(=初回実行)。"""
    path = Path(path)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return datetime.fromisoformat(data["last_checked_utc"])


def save_last_checked(when: datetime, path: str | Path = DEFAULT_STATE_PATH) -> None:
    """今回の実行開始時刻を次回のチェックポイントとして保存する。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"last_checked_utc": when.astimezone(timezone.utc).isoformat()}, ensure_ascii=False),
        encoding="utf-8",
    )
