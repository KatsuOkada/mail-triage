"""夜間実行のきっかけ(Raspberry Pi の systemd タイマーから呼ぶ)。

常駐の Web サーバーに実行を頼む(実行中の状態を画面に出し、手動実行と重ならないようにするため)。
Web サーバーが動いていなければ、この場で直接実行する。
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

PORT = int(os.environ.get("MAIL_TRIAGE_WEB_PORT", "8765"))


def main() -> None:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/run?trigger=nightly", method="POST")
        with urllib.request.urlopen(req, timeout=10) as res:
            print(json.loads(res.read()))
        return
    except OSError as e:
        print(f"Web サーバーに頼めなかったため、直接実行します: {e}")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run_batch

    run_batch.main()


if __name__ == "__main__":
    main()
