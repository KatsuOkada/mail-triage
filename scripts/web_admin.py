"""Web 画面の合言葉と登録済み端末を管理する(Raspberry Pi で実行する)。

  python scripts/web_admin.py set-passphrase   合言葉を決める・変える(入力は画面に出ない)
  python scripts/web_admin.py list             登録済みの端末の一覧
  python scripts/web_admin.py revoke <ID>      端末の登録を取り消す(なくした・買い替えたとき)
"""
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mail_triage.web_app import WebCore

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MAIL_TRIAGE_DATA_DIR", ROOT))


def main(argv: list[str]) -> int:
    core = WebCore(DATA_DIR, DATA_DIR / "logs", ROOT / "config" / "classification_rules.json", runner=lambda p: None)
    if argv[:1] == ["set-passphrase"]:
        first = getpass.getpass("新しい合言葉: ")
        if len(first) < 6:
            print("6文字以上にしてください。")
            return 1
        if getpass.getpass("もう一度: ") != first:
            print("一致しません。")
            return 1
        core.set_passphrase(first)
        print("合言葉を設定しました。")
        return 0
    if argv[:1] == ["list"]:
        for d in core.devices():
            print(f"{d['id']}  {d['name']:<16} {'開発PC' if d.get('dev') else '':<6} 登録 {d['registered']}  最終 {d.get('last_used') or '-'}")
        return 0
    if argv[:1] == ["revoke"] and len(argv) == 2:
        print("取り消しました。" if core.revoke(argv[1]) else "その ID の端末はありません。")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
