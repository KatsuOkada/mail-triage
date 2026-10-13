from unittest.mock import MagicMock

import httplib2
import pytest
from googleapiclient.errors import HttpError

from mail_triage import gmail_client
from mail_triage.gmail_client import (
    _is_transient_error,
    bulk_mark_read_and_archive,
    get_message_metadata,
    modify_labels,
)


def _http_error(status: int) -> HttpError:
    resp = httplib2.Response({"status": status})
    resp.status = status
    return HttpError(resp, b"error body")


def _mock_service(headers: list[dict], snippet: str = "s") -> MagicMock:
    service = MagicMock()
    service.users().messages().get().execute.return_value = {
        "id": "m1",
        "threadId": "t1",
        "snippet": snippet,
        "labelIds": ["INBOX"],
        "payload": {"headers": headers},
    }
    return service


def test_reads_standard_capitalized_headers():
    service = _mock_service(
        [
            {"name": "From", "value": "Someone <a@example.com>"},
            {"name": "Subject", "value": "Hello"},
            {"name": "Date", "value": "Tue, 22 Sep 2026 09:00:00 +0900"},
        ]
    )

    record = get_message_metadata(service, "m1")

    assert record["sender"] == "a@example.com"
    assert record["subject"] == "Hello"
    assert record["date"] == "Tue, 22 Sep 2026 09:00:00 +0900"


def test_reads_lowercase_headers():
    # 送信元によってはヘッダー名を小文字で送ってくることがある。
    # メールヘッダー名は本来大文字小文字を区別しない(RFC 5322)ため、これも正しく読めるべき。
    service = _mock_service(
        [
            {"name": "from", "value": '"Example Pay" <notice@mail.example-pay.jp>'},
            {"name": "subject", "value": "ご利用状況のお知らせ"},
            {"name": "date", "value": "Thu, 01 Jan 2026 12:00:00 +0900"},
        ]
    )

    record = get_message_metadata(service, "m1")

    assert record["sender"] == "notice@mail.example-pay.jp"
    assert record["subject"] == "ご利用状況のお知らせ"
    assert record["date"] == "Thu, 01 Jan 2026 12:00:00 +0900"


def test_is_transient_error_true_for_5xx():
    assert _is_transient_error(_http_error(502)) is True
    assert _is_transient_error(_http_error(503)) is True


def test_is_transient_error_false_for_4xx():
    assert _is_transient_error(_http_error(404)) is False


def test_is_transient_error_false_for_non_http_errors():
    assert _is_transient_error(ValueError("boom")) is False


def test_modify_labels_retries_transient_error_then_succeeds(monkeypatch):
    monkeypatch.setattr(gmail_client.time, "sleep", lambda s: None)
    service = MagicMock()
    attempts = {"n": 0}

    def execute():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _http_error(502)
        return {}

    service.users().messages().modify().execute.side_effect = execute

    modify_labels(service, "m1", remove=["UNREAD"])

    assert attempts["n"] == 3


def test_modify_labels_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr(gmail_client.time, "sleep", lambda s: None)
    service = MagicMock()
    service.users().messages().modify().execute.side_effect = _http_error(502)

    with pytest.raises(HttpError):
        modify_labels(service, "m1", remove=["UNREAD"], max_retries=2)


def test_modify_labels_does_not_retry_permanent_error(monkeypatch):
    monkeypatch.setattr(gmail_client.time, "sleep", lambda s: None)
    service = MagicMock()
    attempts = {"n": 0}

    def execute():
        attempts["n"] += 1
        raise _http_error(404)

    service.users().messages().modify().execute.side_effect = execute

    with pytest.raises(HttpError):
        modify_labels(service, "m1", remove=["UNREAD"])

    assert attempts["n"] == 1


def test_bulk_mark_read_and_archive_continues_after_one_failure(monkeypatch):
    calls = []

    def fake_mark(service, message_id, dry_run):
        calls.append(message_id)
        if message_id == "bad":
            raise RuntimeError("boom")

    monkeypatch.setattr(gmail_client, "mark_read_and_archive", fake_mark)

    succeeded, failed = bulk_mark_read_and_archive(MagicMock(), ["m1", "bad", "m2"])

    assert calls == ["m1", "bad", "m2"]
    assert succeeded == ["m1", "m2"]
    assert failed == ["bad"]
