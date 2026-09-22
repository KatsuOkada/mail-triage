"""
受信箱内の全メールから、以前のGmailフィルタが付けていた旧ユーザーラベルを削除する。
システムラベル(INBOX/UNREAD/IMPORTANT/CATEGORY_*)は対象外(既読/未読・受信箱の状態は変更しない)。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from mail_triage.gmail_client import batch_remove_labels, get_service, list_labels, list_message_ids

OLD_LABEL_NAMES = [
    "大学関連",
    "amazon",
    "購入・領収書",
    "メルマガ/セール",
    "FX",
    "技術ニュース",
    "就活",
    "勤務先",
    "就活・転職",
    "重要/確認",
    "転居",
    "ネットショップ",
]


def main() -> None:
    service = get_service()
    labels = list_labels(service)

    label_ids = [labels[name] for name in OLD_LABEL_NAMES if name in labels]
    missing = [name for name in OLD_LABEL_NAMES if name not in labels]
    if missing:
        print(f"注意: 見つからなかったラベル名(スキップ): {missing}")

    message_ids = list_message_ids(service, "in:inbox")
    print(f"受信箱内{len(message_ids)}件から、{len(label_ids)}個の旧ラベルを削除します。")

    batch_remove_labels(service, message_ids, label_ids)
    print("完了。")


if __name__ == "__main__":
    main()
