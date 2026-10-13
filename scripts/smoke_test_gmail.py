"""
実際のGmailアカウントに接続し、inbox内のメールを取得・分類できるか確認する。
dry_run: true 前提で、既読化・アーカイブ・ラベル付与などの変更は一切行わない。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.stdout is not None:  # pythonw.exe経由で起動された場合、stdoutがNoneになりうるため
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from mail_triage.batch import fetch_inbox_records
from mail_triage.config_loader import load_config
from mail_triage.gmail_client import get_service
from mail_triage.runner import process_record

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    config = load_config(ROOT / "config" / "classification_rules.json")
    service = get_service()

    records = fetch_inbox_records(service, config)
    print(f"inbox内{len(records)}件が見つかりました。\n")

    for record in records[:5]:
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
