"""
初回のGmail OAuth認証を行い、トークンをconfig/gmail_token.jsonに保存する。

実行するとブラウザが開くので、対象のGoogleアカウントでログインし、
「このアプリは確認されていません」という警告が出たら
「詳細設定」→「(アプリ名)に移動(安全ではないページ)」を選んで同意してください。
(このアプリは自分専用に作ったもので、Google側の審査対象ではないため
この警告が出るのは想定通りです)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mail_triage.gmail_client import authorize


def main() -> None:
    creds = authorize()
    print("認証に成功し、トークンを保存しました。")
    print("scopes:", creds.scopes)


if __name__ == "__main__":
    main()
