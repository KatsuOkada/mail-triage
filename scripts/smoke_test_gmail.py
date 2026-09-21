"""
実際のGmailアカウントに接続し、直近のメールを数件取得できるか確認する。
dry_run: true 前提で、既読化・アーカイブ・ラベル付与などの変更は一切行わない。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from mail_triage.config_loader import load_config
from mail_triage.gmail_client import get_message_metadata, get_service, list_message_ids
from mail_triage.models import MailRecord
from mail_triage.runner import process_record

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    config = load_config(ROOT / "config" / "classification_rules.json")
    service = get_service()

    ids = list_message_ids(service, "in:inbox newer_than:1d")
    print(f"直近1日で{len(ids)}件のメールが見つかりました。先頭5件を処理します。\n")

    for message_id in ids[:5]:
        meta = get_message_metadata(service, message_id)
        record = MailRecord(**meta)
        process_record(record, config)
        print(
            f"件名: {record.subject}\n"
            f"送信元: {record.sender}\n"
            f"category={record.category}({record.category_source}) "
            f"verdict={record.verdict}({record.verdict_source})"
            + (f" conf={record.jev_confidence:.2f}" if record.jev_confidence is not None else "")
        )
        print("-" * 40)


if __name__ == "__main__":
    main()
