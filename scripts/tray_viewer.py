"""開発PC のタスクトレイに常駐し、Raspberry Pi で動く mail-triage の結果画面を開くだけのアプリ。

- アイコンをクリック(または右クリック →「結果を表示」)で、結果画面を Chrome のアプリ用ウィンドウで開く
  (Chrome がなければ Edge、どちらもなければ既定のブラウザ)。画面内のメールのリンクも同じブラウザで開く。手動実行・一括アーカイブは開いた画面から行う
- 開く先は .env の MAIL_TRIAGE_WEB_URL(例: http://<Pi のアドレス>:8765/)
- ログオン時に起動するには、スタートアップに `pythonw scripts/tray_viewer.py` のショートカットを置く

使い方:
  pythonw scripts/tray_viewer.py
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_PROGRAM_DIRS = [
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
] + ([Path(os.environ["LOCALAPPDATA"])] if os.environ.get("LOCALAPPDATA") else [])
# 先にあるものを使う(Chrome → Edge)
BROWSERS = [
    ("chrome", "Google/Chrome/Application/chrome.exe"),
    ("msedge", "Microsoft/Edge/Application/msedge.exe"),
]


def load_url(env_path: Path = ROOT / ".env") -> str | None:
    """環境変数か .env の MAIL_TRIAGE_WEB_URL を返す。http(s) でなければ None。"""
    url = os.environ.get("MAIL_TRIAGE_WEB_URL")
    if not url and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "MAIL_TRIAGE_WEB_URL":
                url = value.strip().strip('"').strip("'")
    if url and url.startswith(("http://", "https://")):
        return url
    return None


def find_browser() -> str | None:
    for name, rel in BROWSERS:
        found = shutil.which(name) or next(
            (str(d / rel) for d in _PROGRAM_DIRS if (d / rel).exists()), None
        )
        if found:
            return found
    return None


def open_view(url: str) -> None:
    browser = find_browser()
    if browser:
        subprocess.Popen(
            [browser, f"--app={url}"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        webbrowser.open(url)


def _make_icon_image():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 61, 61), radius=10, fill=(44, 93, 143, 255))
    d.rectangle((12, 20, 52, 46), fill=(255, 255, 255, 255))
    d.line((12, 20, 32, 36, 52, 20), fill=(44, 93, 143, 255), width=4)
    return img


def _single_instance() -> bool:
    """2つ目の起動なら False(Windows の名前付きミューテックスで判定)。"""
    if sys.platform != "win32":
        return True
    ctypes.windll.kernel32.CreateMutexW(None, False, "mail-triage-tray-viewer")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main() -> None:
    import pystray

    if not _single_instance():
        return
    url = load_url()

    def show(icon, item=None):
        if url:
            open_view(url)
        else:
            icon.notify(".env に MAIL_TRIAGE_WEB_URL を書いてください。", "mail-triage")

    menu = pystray.Menu(
        pystray.MenuItem("結果を表示", show, default=True),
        pystray.MenuItem("終了", lambda icon, item: icon.stop()),
    )
    pystray.Icon(
        "mail-triage-viewer", _make_icon_image(), "mail-triage(クリックで結果を表示)", menu
    ).run()


if __name__ == "__main__":
    main()
