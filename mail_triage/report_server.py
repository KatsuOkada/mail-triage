from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from googleapiclient.discovery import Resource

from .config_loader import load_config
from .config_prompt import ROOT, build_config_prompt
from .gmail_client import bulk_mark_read_and_archive
from .log_query import find_currently_unclassified

CONFIG_PATH = ROOT / "config" / "classification_rules.json"

logger = logging.getLogger("mail_triage")


class ServerState:
    """サーバーが今どのレポートを配信するかを保持する。
    トレイアプリの「手動実行」後にreport_html_pathを差し替えられるよう、可変の入れ物にしてある。
    """

    def __init__(self, report_html_path: Path | None, log_dir: Path):
        self.report_html_path = report_html_path
        self.log_dir = log_dir


def _copy_to_clipboard(text: str) -> None:
    subprocess.run(["clip"], input=text.encode("utf-16-le"), check=True)


def _open_terminal_at_root() -> None:
    """claudeコマンドを起動した状態でターミナルを開く。
    生のcmd.exeにプロンプトを貼り付けると各行が個別のコマンドとして実行されてしまうため、
    claudeの対話画面に直接貼り付けられるようにしておく。
    claudeがこのサーバープロセスのPATHに無い場合は素のcmdが残るだけなので実害はない
    (PATHを更新した直後は、そのPATH変更後に新しく起動したサーバーでないと反映されない点に注意)。
    """
    subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", f"cd /d {ROOT} && claude"], shell=False)


def _find_vscode() -> str | None:
    found = shutil.which("code")
    if found:
        return found
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidate = Path(local_app_data) / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd"
        if candidate.exists():
            return str(candidate)
    return None


def open_in_editor(path: Path) -> str:
    """VS Codeが見つかればそれで、無ければメモ帳でファイルを開く。使ったエディタ名を返す。"""
    no_window = subprocess.CREATE_NO_WINDOW
    vscode = _find_vscode()
    if vscode:
        subprocess.Popen([vscode, str(path)], creationflags=no_window)
        return "VS Code"
    subprocess.Popen(["notepad.exe", str(path)], creationflags=no_window)
    return "メモ帳"


_NO_REPORT_HTML = (
    "<!DOCTYPE html><html lang=\"ja\"><head><meta charset=\"utf-8\">"
    "<title>mail-triage</title></head><body>"
    "<p>まだ実行結果がありません。トレイアイコンの「手動実行」を行ってください。</p>"
    "</body></html>"
).encode("utf-8")


def _make_handler(service: Resource, state: ServerState):
    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, obj: dict) -> None:
            body = json.dumps(obj).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length) or b"{}") if length else {}

        def do_GET(self) -> None:
            body = state.report_html_path.read_bytes() if state.report_html_path else _NO_REPORT_HTML
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            payload = self._read_json_body()

            if self.path == "/actions/bulk_archive":
                message_ids = payload.get("message_ids")
                if not message_ids:
                    self._send_json({"ok": False, "error": "message_ids is required"})
                    return
                # レビュー済みの明示的な操作のため、config.dry_run の値に関わらず必ず実行する。
                # Gmail側の一時的なエラー(502等)はmodify_labels側で自動リトライ済み。
                # それでも失敗したメールが1件あっても全体を止めず、残りは処理を続ける。
                succeeded, failed = bulk_mark_read_and_archive(service, message_ids)
                logger.info("一括既読・アーカイブ: 成功%d件 / 失敗%d件", len(succeeded), len(failed))
                self._send_json({"ok": True, "count": len(succeeded), "failed_count": len(failed)})
            elif self.path == "/actions/launch_claude_config":
                try:
                    # クライアントから受け取った件数は使わず、クリック時点のconfigとログ全体から
                    # 都度その場で計算する(レポートページのスナップショットに依存すると値が古くなるため)。
                    config = load_config(CONFIG_PATH)
                    unclassified = find_currently_unclassified(state.log_dir, config)
                    prompt = build_config_prompt(state.log_dir, unclassified)
                    _copy_to_clipboard(prompt)
                    _open_terminal_at_root()
                    logger.info("設定更新用プロンプトをクリップボードにコピーしターミナルを起動(未分類%d件)", len(unclassified))
                    self._send_json({"ok": True, "unclassified_count": len(unclassified)})
                except Exception as e:  # noqa: BLE001
                    logger.exception("Claude起動処理に失敗")
                    self._send_json({"ok": False, "error": str(e)})
            elif self.path == "/actions/open_config":
                try:
                    editor = open_in_editor(CONFIG_PATH)
                    logger.info("設定ファイルを%sで開きました。", editor)
                    self._send_json({"ok": True, "editor": editor})
                except Exception as e:  # noqa: BLE001
                    logger.exception("設定ファイルを開けませんでした")
                    self._send_json({"ok": False, "error": str(e)})
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            pass

    return Handler


def start_server(service: Resource, state: ServerState, port: int = 8765) -> HTTPServer:
    """サーバーをバックグラウンドスレッドで起動して返す。呼び出し側がライフサイクル
    (state.report_html_pathの差し替え、httpd.shutdown()での終了)を管理する。
    """
    handler = _make_handler(service, state)
    httpd = HTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def serve_report(
    service: Resource,
    report_html_path: Path,
    log_dir: Path,
    port: int = 8765,
) -> None:
    """レポートHTMLとアクションAPI(一括アーカイブ・Claude起動)をローカルに配信する。
    対象メッセージIDや未分類件数はクリックした瞬間にサーバー側で計算する
    (サーバー自身はレポートファイルを読んで返すだけの薄い作り)。
    Ctrl+Cで終了するまで動き続ける、手動レビュー用のサーバー(CLI向けの単純な起動経路)。
    """
    state = ServerState(report_html_path, log_dir)
    httpd = start_server(service, state, port)
    url = f"http://127.0.0.1:{port}/"
    print(f"レポートを表示します: {url} (Ctrl+Cで終了)")
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        httpd.server_close()
