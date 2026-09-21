from __future__ import annotations

from email.utils import parseaddr
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

# gmail.modify: 読み取り+ラベル変更(既読化・アーカイブ・ラベル付与)が可能。
# 完全削除やアカウント設定変更は含まれない。
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

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

    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
    _, sender_email = parseaddr(headers.get("From", ""))

    return {
        "message_id": msg["id"],
        "thread_id": msg["threadId"],
        "sender": sender_email,
        "subject": headers.get("Subject", ""),
        "snippet": msg.get("snippet", ""),
        "date": headers.get("Date", ""),
        "label_ids": msg.get("labelIds", []),
    }


def modify_labels(
    service: Resource,
    message_id: str,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> None:
    body: dict[str, list[str]] = {}
    if add:
        body["addLabelIds"] = list(add)
    if remove:
        body["removeLabelIds"] = list(remove)
    if not body:
        return
    service.users().messages().modify(userId="me", id=message_id, body=body).execute()


def mark_read_and_archive(service: Resource, message_id: str, dry_run: bool) -> None:
    """確認不要メールの既読化・アーカイブ。dry_run中は実際には変更しない。"""
    if dry_run:
        return
    modify_labels(service, message_id, remove=["UNREAD", "INBOX"])


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


def apply_category_label(service: Resource, message_id: str, category: str, dry_run: bool) -> None:
    """分類結果をGmailラベルとして書き戻す(段階1のカテゴリ用)。dry_run中は何もしない。"""
    if dry_run:
        return
    label_id = get_or_create_label(service, category)
    modify_labels(service, message_id, add=[label_id])
