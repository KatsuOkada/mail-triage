"""
実際のGmailアカウントに接続し、前回チェック時刻以降の新着メールを取得・分類できるか確認する。
dry_run: true 前提で、既読化・アーカイブ・ラベル付与などの変更は一切行わない。
このスクリプトはテスト用のため、fetch_state(前回チェック時刻)の更新は行わない。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from mail_triage.batch import fetch_new_records
from mail_triage.config_loader import load_config
from mail_triage.gmail_client import get_service
from mail_triage.runner import process_record

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    config = load_config(ROOT / "config" / "classification_rules.json")
    service = get_service()

    records, run_start = fetch_new_records(service, config)
    print(f"新着{len(records)}件が見つかりました(今回の実行開始時刻: {run_start.isoformat()})。")
    print("(このスクリプトはテスト用のため、fetch_stateは更新しません)\n")

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
