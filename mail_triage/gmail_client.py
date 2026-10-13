from __future__ import annotations

import logging
import time
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

logger = logging.getLogger("mail_triage")

# gmail.modify: 読み取り+ラベル変更(既読化・アーカイブ・ラベル付与)が可能。
# gmail.settings.basic: フィルタ等の設定管理に必要(フィルタ削除のため追加)。
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CLIENT_SECRET_PATH = ROOT / "config" / "gmail_oauth_client.json"
DEFAULT_TOKEN_PATH = ROOT / "config" / "gmail_token.json"


def authorize(
    client_secret_path: str | Path = DEFAULT_CLIENT_SECRET_PATH,
    token_path: str | Path = DEFAULT_TOKEN_PATH,
) -> Credentials:
    """初回はブラウザを開いて同意を求め、トークンをtoken_pathに保存する。
    2回目以降はtoken_pathから読み込み、期限切れなら自動更新する。
    """
    token_path = Path(token_path)
    creds: Credentials | None = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return creds


def get_service(creds: Credentials | None = None) -> Resource:
    creds = creds or authorize()
    return build("gmail", "v1", credentials=creds)


def build_query(config: dict[str, Any]) -> str:
    """設定(gmail_fetch)からGmail検索クエリを組み立てる。
    inbox内のメールは処理後(手動または一括アーカイブ)にinbox外へ移動していく運用のため、
    チェックポイントは使わず、inbox内の対象を毎回全件取得する。
    """
    return config["gmail_fetch"]["base_query"]


def list_message_ids(service: Resource, query: str) -> list[str]:
    """Gmail検索クエリに一致するメッセージIDの一覧を取得する(ページング対応)。"""
    ids: list[str] = []
    page_token = None
    while True:
        resp = (
            service.users()
            .messages()
            .list(userId="me", q=query, pageToken=page_token)
            .execute()
        )
        ids.extend(m["id"] for m in resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids


def get_message_metadata(service: Resource, message_id: str) -> dict[str, Any]:
    """判定に必要な最小限の情報(件名・送信元・日付・snippet)を取得する。
    format=metadataを使うため、本文全文の取得・MIMEパースは発生しない。
    """
    msg = (
        service.users()
        .messages()
        .get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        )
        .execute()
    )

    # メールヘッダー名は本来大文字小文字を区別しない(RFC 5322)。送信者によっては
    # "from"/"subject"のように小文字で送ってくることがあるため、小文字化して検索する。
    headers = {h["name"].lower(): h["value"] for h in msg["payload"]["headers"]}
    _, sender_email = parseaddr(headers.get("from", ""))

    return {
        "message_id": msg["id"],
        "thread_id": msg["threadId"],
        "sender": sender_email,
        "subject": headers.get("subject", ""),
        "snippet": msg.get("snippet", ""),
        "date": headers.get("date", ""),
        "label_ids": msg.get("labelIds", []),
    }


def _is_transient_error(exc: Exception) -> bool:
    """502/503等、Gmail側の一時的な障害と思われるエラーかどうか。
    メッセージが見つからない等の恒久的なエラー(4xx)はリトライしても直らないので対象外。
    """
    return isinstance(exc, HttpError) and exc.resp is not None and exc.resp.status >= 500


def modify_labels(
    service: Resource,
    message_id: str,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    max_retries: int = 5,
) -> None:
    body: dict[str, list[str]] = {}
    if add:
        body["addLabelIds"] = list(add)
    if remove:
        body["removeLabelIds"] = list(remove)
    if not body:
        return

    for attempt in range(max_retries):
        try:
            service.users().messages().modify(userId="me", id=message_id, body=body).execute()
            return
        except HttpError as exc:
            if not _is_transient_error(exc) or attempt == max_retries - 1:
                raise
            logger.warning(
                "Gmail APIが一時的なエラーを返しました(%s回目、message_id=%s)。再試行します。",
                attempt + 1, message_id,
            )
            time.sleep(2 * (attempt + 1))


def batch_remove_labels(service: Resource, message_ids: list[str], label_ids: list[str]) -> None:
    """複数メッセージから複数ラベルをまとめて外す(batchModify、1回最大1000件)。"""
    for i in range(0, len(message_ids), 1000):
        chunk = message_ids[i : i + 1000]
        service.users().messages().batchModify(
            userId="me", body={"ids": chunk, "removeLabelIds": label_ids}
        ).execute()


def mark_read_and_archive(service: Resource, message_id: str, dry_run: bool) -> None:
    """確認不要メールの既読化・アーカイブ。dry_run中は実際には変更しない。"""
    if dry_run:
        return
    modify_labels(service, message_id, remove=["UNREAD", "INBOX"])


def bulk_mark_read_and_archive(service: Resource, message_ids: list[str]) -> tuple[list[str], list[str]]:
    """複数メッセージをまとめて既読化・アーカイブする。
    modify_labels側で一時的なエラーは自動リトライ済みだが、それでも失敗した1件があっても
    そこで全体を止めず、残りの処理を続ける。戻り値は(成功したID一覧, 失敗したID一覧)。
    """
    succeeded: list[str] = []
    failed: list[str] = []
    for message_id in message_ids:
        try:
            mark_read_and_archive(service, message_id, dry_run=False)
            succeeded.append(message_id)
        except Exception:  # noqa: BLE001
            logger.exception("既読・アーカイブに失敗しました(スキップして続行します): %s", message_id)
            failed.append(message_id)
    return succeeded, failed


def list_labels(service: Resource) -> dict[str, str]:
    """ラベル名→ラベルIDのマップを返す。"""
    resp = service.users().labels().list(userId="me").execute()
    return {label["name"]: label["id"] for label in resp.get("labels", [])}


def get_or_create_label(service: Resource, name: str) -> str:
    labels = list_labels(service)
    if name in labels:
        return labels[name]
    created = (
        service.users()
        .labels()
        .create(
            userId="me",
            body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
        )
        .execute()
    )
    return created["id"]


def apply_label(service: Resource, message_id: str, label_name: str, dry_run: bool) -> None:
    """指定した名前のラベルを付与する(無ければ作成する)。dry_run中は何もしない。"""
    if dry_run:
        return
    label_id = get_or_create_label(service, label_name)
    modify_labels(service, message_id, add=[label_id])


def apply_category_label(service: Resource, message_id: str, category: str, dry_run: bool) -> None:
    """分類結果をGmailラベルとして書き戻す(段階1のカテゴリ用)。dry_run中は何もしない。"""
    apply_label(service, message_id, category, dry_run)


def list_filters(service: Resource) -> list[dict[str, Any]]:
    """設定済みのGmailフィルタ(自動振り分けルール)を一覧取得する。要gmail.settings.basicスコープ。"""
    resp = service.users().settings().filters().list(userId="me").execute()
    return resp.get("filter", [])


def delete_filter(service: Resource, filter_id: str) -> None:
    """フィルタを1件削除する。元に戻せないので呼び出し前に内容を確認すること。"""
    service.users().settings().filters().delete(userId="me", id=filter_id).execute()
