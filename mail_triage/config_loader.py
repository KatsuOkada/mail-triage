from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REQUIRED_KEYS = {
    "version",
    "dry_run",
    "confidence_threshold",
    "gmail_fetch",
    "sender_categories",
    "importance_rules",
}


def load_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        config = json.load(f)
    _validate(config)
    return config


def _validate(config: dict[str, Any]) -> None:
    missing = REQUIRED_KEYS - config.keys()
    if missing:
        raise ValueError(f"config missing keys: {missing}")

    for rule in config["sender_categories"]:
        re.compile(rule["domain_regex"])  # 不正な正規表現なら例外を送出

    for rule in config["importance_rules"]:
        re.compile(rule["subject_regex"])
        if rule["verdict"] not in ("要確認", "確認不要"):
            raise ValueError(f"invalid verdict in importance_rules: {rule}")
