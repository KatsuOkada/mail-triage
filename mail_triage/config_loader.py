from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# importance_rulesのverdictに書ける、重要度区分以外の値。当たったメールは段階2で確定させず、段階3(Jev)で判定する。
JEV_CHECK = "Jevで確認"

REQUIRED_KEYS = {
    "version",
    "dry_run",
    "jev_enabled",
    "confidence_threshold",
    "gmail_fetch",
    "sender_categories",
    "importance_rules",
    "jev_prompt",
    "verdict_levels",
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

    verdict_names = _validate_verdict_levels(config["verdict_levels"])

    for rule in config["importance_rules"]:
        re.compile(rule["subject_regex"])
        if rule["verdict"] not in verdict_names | {JEV_CHECK}:
            raise ValueError(f"invalid verdict in importance_rules: {rule}")

    _validate_jev_body(config.get("jev_body", {}))

    jev_prompt = config["jev_prompt"]
    if "instructions" not in jev_prompt or "criteria" not in jev_prompt:
        raise ValueError("jev_prompt must have 'instructions' and 'criteria'")
    if set(jev_prompt["criteria"].keys()) != verdict_names:
        raise ValueError(f"jev_prompt.criteria must have exactly the keys {verdict_names}")


def _validate_jev_body(jev_body: dict[str, Any]) -> None:
    """Jevに渡す本文の設定(省略可)。max_charsは正の整数、redact_regexesは正規表現の配列。"""
    max_chars = jev_body.get("max_chars", 1)
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars <= 0:
        raise ValueError(f"jev_body.max_chars must be a positive integer: {max_chars!r}")
    redact_regexes = jev_body.get("redact_regexes", [])
    if not isinstance(redact_regexes, list):
        raise ValueError("jev_body.redact_regexes must be a list")
    for pattern in redact_regexes:
        re.compile(pattern)


def _validate_verdict_levels(levels: list[dict[str, Any]]) -> set[str]:
    """重要度区分(名前・優先順位・ラベル付与要否・アーカイブ要否)の定義を検証する。
    配列の並び順がそのまま表示の順(先頭が上)になる。
    「要確認」「確認不要」は表示上の2大項目そのものであるため必ず含み、
    それ以外の区分(例:重要,技術ニュース)は display_group でどちらかに属する必要がある。
    """
    names = [level["name"] for level in levels]
    if len(names) != len(set(names)):
        raise ValueError("verdict_levels names must be unique")
    if "要確認" not in names or "確認不要" not in names:
        raise ValueError("verdict_levels must include '要確認' and '確認不要'")

    for level in levels:
        for key in ("name", "display_group", "apply_label"):
            if key not in level:
                raise ValueError(f"verdict_levels entry missing '{key}': {level}")
        if level["name"] in ("要確認", "確認不要"):
            if level["display_group"] != level["name"]:
                raise ValueError(f"'{level['name']}' must have display_group equal to itself")
        elif level["display_group"] not in ("要確認", "確認不要"):
            raise ValueError(f"invalid display_group in verdict_levels entry: {level}")

    return set(names)
