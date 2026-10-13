from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import webbrowser
from pathlib import Path

import pystray
from googleapiclient.discovery import Resource
from PIL import Image, ImageDraw

from .batch_runner import run_once
from .config_loader import load_config
from .report_server import ServerState, start_server

logger = logging.getLogger("mail_triage")


def _is_process_running(pid: int) -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FI", "IMAGENAME eq pythonw.exe", "/NH"],
        capture_output=True,
        text=True,
    )
    return str(pid) in result.stdout


def _ensure_single_instance(lock_path: Path) -> None:
    """他に起動中のtray_appインスタンスがあれば強制終了してから、自分のPIDを書き込む。

    タスクスケジューラのMultipleInstancesPolicy(StopExisting)だけでは、ログオン経由などで
    起動した既存インスタンスを確実には停止できないことがある(実際に、ログオン起動分と
    定時起動分の2つのトレイアイコンが同時に生き残り、片方の古いレポートが表示され続ける
    不具合が発生した)。そのため、アプリ自身の起動時にも多重起動を防ぐ。
    """
    if lock_path.exists():
        old_pid_text = lock_path.read_text(encoding="utf-8").strip()
        if old_pid_text.isdigit():
            old_pid = int(old_pid_text)
            if old_pid != os.getpid() and _is_process_running(old_pid):
                logger.info("既存のトレイアプリ(PID %d)を停止します。", old_pid)
                subprocess.run(["taskkill", "/PID", str(old_pid), "/F"], capture_output=True)
    lock_path.write_text(str(os.getpid()), encoding="utf-8")


def _make_icon_image() -> Image.Image:
    """簡易的なトレイアイコン画像を生成する(専用の画像ファイルは用意していない)。"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((2, 2, 61, 61), fill=(41, 128, 185, 255))
    draw.text((22, 16), "M", fill=(255, 255, 255, 255))
    return img


def _toggle_config_flag(config_path: Path, key: str) -> bool:
    """設定ファイルの空行によるグループ分けなど、手作業で整えた整形を壊さないよう、
    JSON全体を読み書きし直すのではなく該当のtrue/falseだけを文字列置換で反転する。
    戻り値は変更後の値。
    """
    text = config_path.read_text(encoding="utf-8")
    pattern = re.compile(rf'("{key}"\s*:\s*)(true|false)')
    match = pattern.search(text)
    if not match:
        raise ValueError(f"'{key}' が設定ファイル内に見つかりません")
    new_value = "false" if match.group(2) == "true" else "true"
    new_text = text[: match.start(2)] + new_value + text[match.end(2) :]
    config_path.write_text(new_text, encoding="utf-8")
    return new_value == "true"


def run_tray_app(
    service: Resource,
    config_path: Path,
    log_dir: Path,
    initial_report_path: Path | None,
    port: int = 8765,
    auto_run_on_start: bool = False,
) -> None:
    """サーバーを起動しつつ、タスクトレイアイコン(実行結果の再表示・手動実行・
    Jev利用/ドライモードの切り替え)を表示する。トレイの「終了」を選ぶまで動き続ける。

    auto_run_on_start=True の場合、アイコン表示直後に「手動実行」と同じ処理を自動で1回行う
    (タスクスケジューラによる夜間の定時実行から起動する想定)。
    """
    _ensure_single_instance(log_dir / "tray.lock")
    state = ServerState(initial_report_path, log_dir)
    httpd = start_server(service, state, port)
    url = f"http://127.0.0.1:{port}/"

    def show_report(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if state.report_html_path is None:
            icon.notify("まだ実行結果がありません。先に「手動実行」を行ってください。", "mail-triage")
            return
        webbrowser.open(url)

    def do_run(icon: pystray.Icon) -> None:
        icon.notify("バッチ処理を実行しています...", "mail-triage")
        try:
            report_path = run_once(service, config_path, log_dir)
            state.report_html_path = report_path
            icon.notify("処理が完了しました。結果をブラウザで開きます。", "mail-triage")
            webbrowser.open(url)
        except Exception as e:  # noqa: BLE001
            logger.exception("バッチ実行に失敗しました。")
            icon.notify(f"エラー: {e}", "mail-triage")

    def manual_run(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        threading.Thread(target=do_run, args=(icon,), daemon=True).start()

    def toggle_jev(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        new_value = _toggle_config_flag(config_path, "jev_enabled")
        icon.notify(f"Jev利用: {'ON' if new_value else 'OFF'}", "mail-triage")

    def toggle_dry_run(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        new_value = _toggle_config_flag(config_path, "dry_run")
        icon.notify(f"ドライモード: {'ON' if new_value else 'OFF'}", "mail-triage")

    def is_jev_enabled(item: pystray.MenuItem) -> bool:
        return load_config(config_path)["jev_enabled"]

    def is_dry_run(item: pystray.MenuItem) -> bool:
        return load_config(config_path)["dry_run"]

    def exit_app(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        httpd.shutdown()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("実行結果を表示", show_report, default=True),
        pystray.MenuItem("手動実行", manual_run),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Jev利用", toggle_jev, checked=is_jev_enabled),
        pystray.MenuItem("ドライモード", toggle_dry_run, checked=is_dry_run),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("終了", exit_app),
    )

    icon = pystray.Icon("mail-triage", _make_icon_image(), "mail-triage", menu)

    if auto_run_on_start:

        def _setup(icon: pystray.Icon) -> None:
            icon.visible = True
            threading.Thread(target=do_run, args=(icon,), daemon=True).start()

        icon.run(setup=_setup)
    else:
        icon.run()
