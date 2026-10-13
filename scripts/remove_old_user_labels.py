"""
受信箱内の全メールから、以前のGmailフィルタが付けていた旧ユーザーラベルを削除する。
システムラベル(INBOX/UNREAD/IMPORTANT/CATEGORY_*)は対象外(既読/未読・受信箱の状態は変更しない)。

使い方(ラベル名は個人の情報なのでコードには書かず、引数で渡す):
  python scripts/remove_old_user_labels.py ラベル名1 ラベル名2 ...
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.stdout is not None:  # pythonw.exe経由で起動された場合、stdoutがNoneになりうるため
    sys.stdout.reconfigure(encoding="utf-8")

from mail_triage.gmail_client import batch_remove_labels, get_service, list_labels, list_message_ids


def main() -> None:
    old_label_names = sys.argv[1:]
    if not old_label_names:
        sys.exit("削除するラベル名を引数で指定してください。")

    service = get_service()
    labels = list_labels(service)

    label_ids = [labels[name] for name in old_label_names if name in labels]
    missing = [name for name in old_label_names if name not in labels]
    if missing:
        print(f"注意: 見つからなかったラベル名(スキップ): {missing}")

    message_ids = list_message_ids(service, "in:inbox")
    print(f"受信箱内{len(message_ids)}件から、{len(label_ids)}個の旧ラベルを削除します。")

    batch_remove_labels(service, message_ids, label_ids)
    print("完了。")


if __name__ == "__main__":
    main()
