from __future__ import annotations

import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

from .models import MailRecord

load_dotenv()

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"


def _build_payload(record: MailRecord, config: dict[str, Any]) -> dict[str, Any]:
    prompt_config = config["jev_prompt"]
    # 本文を取得済みならそれを、無ければGmailのsnippet(本文冒頭の抜粋)を渡す
    body = record.body if record.body is not None else record.snippet
    state = f"件名: {record.subject}\n送信元: {record.sender}\n本文: {body}"
    return {
        "model": MODEL,
        "state": state,
        "questions": {
            "triage_level": {
                "type": "choice",
                "instructions": prompt_config["instructions"],
                "criteria": prompt_config["criteria"],
            }
        },
    }


def classify_verdict_by_jev(
    record: MailRecord,
    config: dict[str, Any],
    api_key: str | None = None,
) -> MailRecord:
    """段階3: 段階1,2で確定しなかったメールをJevで判定する(重要/要確認/確認不要の3択)。
    verdictが既に埋まっている場合は何もしない(段階2までで確定済み)。
    判定基準(instructions/criteria)はconfig.jev_promptに外だししてあり、
    パーソナライズしたい場合はconfigファイルの編集だけで済む。
    """
    if record.verdict is not None:
        return record

    api_key = api_key or os.environ["TYPESAFE_API_KEY"]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = _build_payload(record, config)

    resp = None
    last_exc: requests.RequestException | None = None
    for attempt in range(5):
        try:
            resp = requests.post(URL, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(3 * (attempt + 1))
    else:
        assert last_exc is not None
        raise last_exc

    data = resp.json()
    answer = data["answers"]["triage_level"]

    record.verdict = answer["choice"]
    record.verdict_source = "jev"
    record.jev_probabilities = answer["probabilities"]
    record.jev_confidence = answer["confidence"]
    record.low_confidence_flag = record.jev_confidence < config["confidence_threshold"]
    return record
