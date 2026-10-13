from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


def setup_logging(log_dir: str | Path, run_time: datetime | None = None) -> logging.Logger:
    """バッチ実行自体の動作ログ(起動・件数・エラー等)を logs/ 配下に記録する。
    判定結果(MailRecord)を記録する decision_logger とは別物。
    個人情報を含む可能性があるため、出力先は decision_logger と同じ logs/ 配下にまとめる(gitignore済み)。
    1回の実行ごとに実行時刻付きのファイル名(YYYY-MM-DD_HHMMSS_run.log)に書き出すため、
    同じ日に複数回実行しても前回の記録を上書きしない。
    """
    run_time = run_time or datetime.now()
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{run_time.strftime('%Y-%m-%d_%H%M%S')}_run.log"

    logger = logging.getLogger("mail_triage")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
