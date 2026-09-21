from __future__ import annotations

import os
import time
from typing import Any

import requests

from .models import MailRecord

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"


def _build_payload(record: MailRecord) -> dict[str, Any]:
    state = f"件名: {record.subject}\n送信元: {record.sender}\n本文: {record.snippet}"
    return {
        "model": MODEL,
        "state": state,
        "questions": {
            "need_check": {
                "type": "noul",
                "instructions": "受信者(会社員)がこのメールの内容を確認する必要があるか?",
                "criteria": {
                    "true": "締切や金銭、業務上必須の対応が伴う内容",
                    "false": "広告・キャンペーン・任意参加の案内など、確認しなくても実害がない内容",
                },
            }
        },
    }


def classify_verdict_by_jev(
    record: MailRecord,
    config: dict[str, Any],
    api_key: str | None = None,
) -> MailRecord:
    """段階3: 段階1,2で確定しなかったメールをJevで判定する。
    verdictが既に埋まっている場合は何もしない(段階2までで確定済み)。
    """
    if record.verdict is not None:
        return record

    api_key = api_key or os.environ["TYPESAFE_API_KEY"]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = _build_payload(record)

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
    prob = data["answers"]["need_check"]["noul"]
    confidence = abs(prob - 0.5) * 2

    record.jev_probability = prob
    record.jev_confidence = confidence
    record.verdict = "要確認" if prob >= 0.5 else "確認不要"
    record.verdict_source = "jev"
    record.low_confidence_flag = confidence < config["confidence_threshold"]
    return record
