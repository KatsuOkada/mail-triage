"""
本番実装(mail_triageパッケージ)のパイプラインを、既存の評価データセットに通して
これまでの実験結果(96%以上の精度)を再現できるか検証する。
"""
import csv
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

from mail_triage.config_loader import load_config
from mail_triage.models import MailRecord
from mail_triage.runner import process_record

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "classification_rules.json"
IMPORTANT_TRUE_WORDS = {"true", "重要"}


def load_eval_rows() -> list[dict]:
    rows = []
    for fn in ["eval_set.csv", "eval_set_2.csv"]:
        with io.open(ROOT / "experiments" / fn, encoding="utf-8-sig", newline="") as f:
            rows.extend(csv.DictReader(f))
    return rows


def main() -> None:
    config = load_config(CONFIG_PATH)
    rows = load_eval_rows()

    correct = 0
    false_negatives = []
    false_positives = []
    rule_confirmed = 0
    jev_used = 0
    unclassified = 0

    for row in rows:
        gt_check_needed = row["your_importance(重要/非重要)"].strip() in IMPORTANT_TRUE_WORDS
        record = MailRecord(
            message_id=row["no"],
            thread_id=row["no"],
            sender=row["sender"],
            subject=row["subject"],
            snippet=row["snippet"],
            date="2026-09-22T00:00:00Z",
        )
        process_record(record, config)

        if record.category is None:
            unclassified += 1
            print(f"#{row['no']:>2} UNCLASSIFIED sender={row['sender']}")
            continue

        if record.verdict_source == "rule":
            rule_confirmed += 1
        elif record.verdict_source == "jev":
            jev_used += 1

        pred_check_needed = record.verdict == "要確認"
        mark = "OK" if pred_check_needed == gt_check_needed else "NG"
        if mark == "NG":
            if gt_check_needed:
                false_negatives.append((row["no"], row["subject"]))
            else:
                false_positives.append((row["no"], row["subject"]))
        else:
            correct += 1

        conf = f"conf={record.jev_confidence:.2f}" if record.jev_confidence is not None else ""
        print(f"#{row['no']:>2} [{mark}] category={record.category} verdict={record.verdict}"
              f"({record.verdict_source}) {conf} 正解={'要確認' if gt_check_needed else '確認不要'}")

    n = len(rows) - unclassified
    print(f"\n===== 検証結果 =====")
    print(f"総件数: {len(rows)}件(うち未分類{unclassified}件)")
    print(f"Rule Classifierで確定: {rule_confirmed}件 / Jevで判定: {jev_used}件")
    print(f"Accuracy: {correct}/{n} ({correct/n:.1%})")
    print(f"False Negative(見逃し): {len(false_negatives)}件")
    for no, subj in false_negatives:
        print(f"  #{no} {subj}")
    print(f"False Positive: {len(false_positives)}件")
    for no, subj in false_positives:
        print(f"  #{no} {subj}")


if __name__ == "__main__":
    main()
