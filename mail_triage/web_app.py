"""LAN 内の端末(PC・iPad・スマホ)からレポートの表示・手動実行・一括アーカイブを行う Web サーバー。

Raspberry Pi で常駐させる想定。
- 家の LAN(プライベートな IPv4)と自分自身(127.0.0.1)からの接続だけを受け付ける
- 端末は初回だけ合言葉で登録し、以後は Cookie で見分ける。未登録の端末にはメールの内容を出さない
- 実行は同時に 1 つだけ。実行中に「今すぐ実行」が来たら新しくは始めず、実行中のものに相乗りする
- 自分自身(127.0.0.1)からは、実行の依頼と状態の確認だけを登録なしで通す(定時実行のタイマーのため)
- 端末の Cookie は1年で切れるが、使うたびに延長する
"""

from __future__ import annotations

import hashlib
import hmac
import html
import ipaddress
import json
import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs

from .config_loader import load_config
from .config_prompt import build_config_prompt
from .log_query import find_currently_unclassified

logger = logging.getLogger("mail_triage.web")

ROOT = Path(__file__).resolve().parent.parent
COOKIE_NAME = "mt_device"
COOKIE_MAX_AGE = 365 * 24 * 3600  # 使うたびに延長する。1年使わなかった端末は登録し直し
# Pi 自身(127.0.0.1)から登録なしで使えるのは、定時実行のきっかけと状態の確認だけ
LOCAL_PATHS = {"/api/run", "/api/status"}
MAX_FAILURES = 5
LOCKOUT_SECONDS = 15 * 60
REPORT_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})(\d{2})_report\.html$")
NO_CHECK_IDS = re.compile(r"const NO_CHECK_IDS = (\[.*?\]);", re.S)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def hash_passphrase(passphrase: str, salt: bytes | None = None) -> dict[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return {"salt": salt.hex(), "hash": digest.hex()}


def verify_passphrase(passphrase: str, stored: dict[str, str]) -> bool:
    expected = hash_passphrase(passphrase, bytes.fromhex(stored["salt"]))["hash"]
    return hmac.compare_digest(expected, stored["hash"])


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_allowed_client(ip: str) -> bool:
    """家の LAN(プライベートな IPv4)と自分自身だけ通す。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_loopback or (addr.version == 4 and addr.is_private)


def is_loopback(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


class WebCore:
    """画面や HTTP から独立した、状態の持ち主(端末・合言葉・実行の状態・アーカイブ済みの印)。"""

    def __init__(
        self,
        data_dir: Path,
        log_dir: Path,
        config_path: Path,
        runner: Callable[[Callable[[str], None]], Path],
        clock: Callable[[], float] = time.time,
    ):
        self.web_dir = data_dir / "web"
        self.log_dir = log_dir
        self.config_path = config_path
        self.runner = runner
        self.clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._locked_until = 0.0
        self.state: dict[str, Any] = _read_json(self.web_dir / "run_state.json", {"state": "idle"})
        if self.state.get("state") == "running":  # 実行中に止まった場合は失敗として扱う
            self.state = {
                **self.state,
                "state": "failed",
                "error": "実行中にサーバーが止まりました",
            }

    # --- 端末の登録(F-2, F-3, F-14) ---
    @property
    def _devices_path(self) -> Path:
        return self.web_dir / "devices.json"

    def devices(self) -> list[dict[str, Any]]:
        return _read_json(self._devices_path, [])

    def find_device(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        h = _token_hash(token)
        device = next((d for d in self.devices() if hmac.compare_digest(d["token_hash"], h)), None)
        if device is None:
            return None
        last = datetime.fromisoformat(device.get("last_used") or device["registered"])
        if (datetime.now() - last).total_seconds() > COOKIE_MAX_AGE:
            return None  # 1年使っていない端末は無効
        return device

    def touch_device(self, device: dict[str, Any]) -> None:
        with self._lock:
            devices = self.devices()
            for d in devices:
                if d["id"] == device["id"]:
                    d["last_used"] = datetime.now().isoformat(timespec="seconds")
            _write_json(self._devices_path, devices)

    def has_passphrase(self) -> bool:
        return (self.web_dir / "passphrase.json").exists()

    def set_passphrase(self, passphrase: str) -> None:
        _write_json(self.web_dir / "passphrase.json", hash_passphrase(passphrase))

    def register(self, passphrase: str, name: str, is_dev: bool) -> tuple[str | None, str]:
        """合言葉が正しければ端末を登録し、(Cookie に入れるトークン, "") を返す。"""
        with self._lock:
            now = self.clock()
            if now < self._locked_until:
                return (
                    None,
                    f"続けて間違えたため、{int((self._locked_until - now) // 60) + 1}分ほど待ってください。",
                )
            stored = _read_json(self.web_dir / "passphrase.json", None)
            if stored is None:
                return (
                    None,
                    "合言葉がまだ決められていません(Pi で scripts/web_admin.py set-passphrase)。",
                )
            if not verify_passphrase(passphrase, stored):
                self._failures += 1
                if self._failures >= MAX_FAILURES:
                    self._failures = 0
                    self._locked_until = now + LOCKOUT_SECONDS
                    return None, "続けて間違えたため、15分ほど待ってください。"
                return None, "合言葉が違います。"
            self._failures = 0
            token = secrets.token_urlsafe(32)
            devices = self.devices()
            devices.append(
                {
                    "id": secrets.token_hex(4),
                    "name": name.strip()[:40] or "名前なし",
                    "dev": is_dev,
                    "token_hash": _token_hash(token),
                    "registered": datetime.now().isoformat(timespec="seconds"),
                    "last_used": None,
                }
            )
            _write_json(self._devices_path, devices)
            return token, ""

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            devices = self.devices()
            kept = [d for d in devices if d["id"] != device_id]
            _write_json(self._devices_path, kept)
            return len(kept) != len(devices)

    # --- レポート(S-1) ---
    def latest_report(self) -> Path | None:
        reports = sorted(p for p in self.log_dir.glob("*_report.html") if REPORT_NAME.match(p.name))
        return reports[-1] if reports else None

    @staticmethod
    def report_time(path: Path) -> str:
        m = REPORT_NAME.match(path.name)
        return f"{m.group(1)} {m.group(2)}:{m.group(3)}" if m else path.name

    # --- 実行(F-5, F-6, F-7) ---
    def status(self) -> dict[str, Any]:
        latest = self.latest_report()
        return {
            **self.state,
            "report": latest.name if latest else None,
            "report_time": self.report_time(latest) if latest else None,
        }

    def start_run(self, trigger: str) -> bool:
        """実行を始める。すでに実行中なら何もせず False(相乗り)。"""
        with self._lock:
            if self.state.get("state") == "running":
                return False
            self.state = {
                "state": "running",
                "trigger": trigger,
                "stage": "準備",
                "started_at": datetime.now().isoformat(timespec="seconds"),
            }
            _write_json(self.web_dir / "run_state.json", self.state)
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _set_stage(self, stage: str) -> None:
        with self._lock:
            self.state = {**self.state, "stage": stage}
            _write_json(self.web_dir / "run_state.json", self.state)

    def _run(self) -> None:
        try:
            self.runner(self._set_stage)
            result = {"state": "succeeded"}
        except Exception as e:  # noqa: BLE001
            logger.exception("実行に失敗しました")
            result = {"state": "failed", "error": f"{type(e).__name__}: {e}"[:300]}
        with self._lock:
            self.state = {
                **self.state,
                **result,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }
            _write_json(self.web_dir / "run_state.json", self.state)

    # --- 一括アーカイブ(F-9) ---
    def archive_targets(self, requested: list[str]) -> tuple[Path | None, list[str]]:
        """最新のレポートの「確認不要」に含まれ、まだアーカイブしていないものだけを返す。"""
        latest = self.latest_report()
        if latest is None:
            return None, []
        m = NO_CHECK_IDS.search(latest.read_text(encoding="utf-8"))
        allowed = set(json.loads(m.group(1))) if m else set()
        done = set(_read_json(self.web_dir / "archived.json", {}).get(latest.name, []))
        return latest, [i for i in requested if i in allowed and i not in done]

    def mark_archived(self, report: Path, ids: list[str]) -> None:
        with self._lock:
            archived = _read_json(self.web_dir / "archived.json", {})
            archived = {
                report.name: sorted(set(archived.get(report.name, [])) | set(ids))
            }  # 最新の分だけ残す
            _write_json(self.web_dir / "archived.json", archived)

    def config_prompt(self) -> tuple[str, int]:
        config = load_config(self.config_path)
        unclassified = find_currently_unclassified(self.log_dir, config)
        prompt = build_config_prompt(self.log_dir, unclassified)
        note = (
            "【注意】この mail-triage は Raspberry Pi で動いています。設定ファイルは Pi の "
            f"{self.config_path} です。開発PC からは ssh でその機械に入って編集してください"
            "(保存すれば次の実行から反映されます)。\n\n"
        )
        return note + prompt, len(unclassified)


# --- 画面 ---
_HEAD_EXTRA = (
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<link rel="manifest" href="/manifest.webmanifest">'
    '<link rel="icon" href="/icon.png"><link rel="apple-touch-icon" href="/icon.png">'
    '<meta name="theme-color" content="#2c5d8f">'
)

_BAR_STYLE = """
<style>
 #mt-bar { position: sticky; top: 0; background: #2c5d8f; color: #fff; padding: .6em 1em; margin: -2em -1em 1em;
           display: flex; flex-wrap: wrap; gap: .6em; align-items: center; z-index: 10; }
 #mt-bar button { margin: 0; background: #fff; color: #2c5d8f; border: 0; border-radius: 4px; font-weight: bold; }
 #mt-run-status { flex: 1 1 12em; font-size: .9em; }
 #mt-fail { background: #fdecea; color: #b03a2e; padding: .5em 1em; border-radius: 4px; display: none; }
 @media (max-width: 600px) { body { margin: 1em auto; } #mt-bar { margin: -1em -1em 1em; } .mail-item { flex-wrap: wrap; } }
</style>
"""

_BAR_SCRIPT = """
<script>
let mtWasRunning = false;
const mtReport = %(report)s;
function mtShow(s) {
  const el = document.getElementById("mt-run-status");
  const btn = document.getElementById("mt-run-btn");
  const fail = document.getElementById("mt-fail");
  if (s.state === "running") {
    const mins = Math.floor((Date.now() - new Date(s.started_at)) / 60000);
    el.textContent = `実行中(${s.trigger === "nightly" ? "定時" : "手動"}、開始 ${s.started_at.slice(11,16)}、${mins}分経過)… ${s.stage}`;
    btn.disabled = true;
    const ab = document.getElementById("bulk-archive-btn"); if (ab) ab.disabled = true;
    mtWasRunning = true;
  } else {
    btn.disabled = false;
    const ab = document.getElementById("bulk-archive-btn"); if (ab) ab.disabled = false;
    el.textContent = s.report_time ? `結果の作成: ${s.report_time}` : "まだ結果がありません";
    if (s.state === "failed") {
      fail.style.display = "block";
      fail.textContent = `前回の実行は失敗しました(${(s.finished_at || "").replace("T", " ").slice(0,16)}): ${s.error}`;
    }
    if ((mtWasRunning || s.report !== mtReport) && s.state === "succeeded" && s.report !== mtReport) location.reload();
    mtWasRunning = false;
  }
}
async function mtPoll() {
  try { const r = await fetch("/api/status"); if (r.ok) mtShow(await r.json()); } catch (e) {}
  setTimeout(mtPoll, mtWasRunning ? 3000 : 30000);
}
async function mtRun() {
  document.getElementById("mt-run-btn").disabled = true;
  const r = await fetch("/api/run", {method: "POST"});
  mtShow(await r.json());
  setTimeout(mtPoll, 2000);
}
if (typeof bulkArchive === "function") {
  const mtOrigArchive = bulkArchive;
  bulkArchive = async function () {
    if (NO_CHECK_IDS.length && !confirm(`確認不要の ${NO_CHECK_IDS.length} 件を既読にしてアーカイブします。よろしいですか?`)) return;
    return mtOrigArchive();
  };
}
%(dev_script)s
mtPoll();
</script>
"""

_DEV_SCRIPT = """
function mtCopy(text) {
  const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta);
  ta.select(); const ok = document.execCommand("copy"); ta.remove(); return ok;
}
launchClaudeConfig = async function () {
  const status = document.getElementById("status");
  status.textContent = "準備中...";
  const r = await fetch("/api/config_prompt"); const d = await r.json();
  status.textContent = mtCopy(d.prompt)
    ? `Claude Code 用の指示をコピーしました(未分類 ${d.unclassified_count}件)。mail-triage のフォルダで claude を起動して貼り付けてください。`
    : "コピーできませんでした。";
};
openConfigFile = function () { window.open("/config/rules", "_blank"); };
"""

_HIDE_DEV_BUTTONS = "<style>#config-btn, #open-config-btn { display: none; }</style>"


def build_report_page(report_html: str | None, report_name: str | None, is_dev: bool) -> str:
    if report_html is None:
        report_html = (
            '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><title>mail-triage</title>'
            "<style>body { font-family: sans-serif; max-width: 720px; margin: 2em auto; padding: 0 1em; }</style>"
            "</head><body><p>まだ結果がありません。「今すぐ実行」を押してください。</p></body></html>"
        )
    bar = (
        '<div id="mt-bar"><span id="mt-run-status">読み込み中…</span>'
        '<button id="mt-run-btn" onclick="mtRun()">今すぐ実行</button></div><div id="mt-fail"></div>'
    )
    script = _BAR_SCRIPT % {
        "report": json.dumps(report_name),
        "dev_script": _DEV_SCRIPT if is_dev else "",
    }
    page = report_html.replace("<head>", "<head>" + _HEAD_EXTRA, 1)
    page = page.replace(
        "</head>", _BAR_STYLE + ("" if is_dev else _HIDE_DEV_BUTTONS) + "</head>", 1
    )
    page = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + bar, page, count=1)
    return page.replace("</body>", script + "</body>", 1)


def build_register_page(message: str = "") -> str:
    msg = f'<p style="color:#b03a2e">{html.escape(message)}</p>' if message else ""
    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">{_HEAD_EXTRA}
<title>mail-triage 端末の登録</title>
<style>body {{ font-family: sans-serif; max-width: 420px; margin: 2em auto; padding: 0 1em; line-height: 1.6; }}
input[type=text], input[type=password] {{ width: 100%; padding: .5em; font-size: 1em; box-sizing: border-box; }}
button {{ margin-top: 1em; padding: .6em 1.2em; font-size: 1em; }}</style></head><body>
<h1>mail-triage</h1>
<p>この端末はまだ登録されていません。合言葉を入れると、この端末を登録します(初回だけ)。</p>
{msg}
<form method="post" action="/register">
<label>合言葉<br><input type="password" name="passphrase" autocomplete="current-password" required></label><br><br>
<label>端末の名前(例: iPad)<br><input type="text" name="name" maxlength="40"></label><br><br>
<label><input type="checkbox" name="dev" value="1"> この端末は開発PC(分類ルールの更新ボタンを出す)</label><br>
<button type="submit">登録する</button>
</form></body></html>"""


def make_icon_png() -> bytes:
    from io import BytesIO

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (192, 192), "#2c5d8f")
    d = ImageDraw.Draw(img)
    d.rectangle([36, 56, 156, 136], fill="#ffffff")
    d.line([36, 56, 96, 104, 156, 56], fill="#2c5d8f", width=8)
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


MANIFEST = json.dumps(
    {
        "name": "mail-triage",
        "short_name": "メール仕分け",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#2c5d8f",
        "icons": [{"src": "/icon.png", "sizes": "192x192", "type": "image/png"}],
    },
    ensure_ascii=False,
).encode("utf-8")


def _cookie(token: str) -> str:
    return f"{COOKIE_NAME}={token}; Max-Age={COOKIE_MAX_AGE}; Path=/; HttpOnly; SameSite=Strict"


def make_handler(core: WebCore, archive: Callable[[list[str]], tuple[list[str], list[str]]]):
    icon = make_icon_png()

    class Handler(BaseHTTPRequestHandler):
        server_version = "mail-triage"

        def _send(
            self, code: int, body: bytes, ctype: str, headers: dict[str, str] | None = None
        ) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            headers = dict(headers or {})
            if self._renew_token and "Set-Cookie" not in headers:
                headers["Set-Cookie"] = _cookie(self._renew_token)  # 使うたびに期限を延ばす
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj: Any, code: int = 200) -> None:
            self._send(
                code,
                json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        def _html(self, text: str, code: int = 200, headers: dict[str, str] | None = None) -> None:
            self._send(code, text.encode("utf-8"), "text/html; charset=utf-8", headers)

        def _client(self) -> str:
            return self.client_address[0]

        _renew_token: str | None = None

        def _device(self) -> dict[str, Any] | None:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            token = cookie[COOKIE_NAME].value if COOKIE_NAME in cookie else None
            device = core.find_device(token)
            if device:
                self._renew_token = token
            return device

        def _gate(self, path: str) -> tuple[bool, dict[str, Any] | None]:
            """(通してよいか, 端末)。LAN の外は 403、未登録は呼び出し側で登録画面へ。"""
            if not is_allowed_client(self._client()):
                self._send(403, b"forbidden", "text/plain")
                return False, None
            if is_loopback(self._client()) and path in LOCAL_PATHS:
                return True, {"id": "local", "name": "local", "dev": False}
            device = self._device()
            if device:
                core.touch_device(device)
            return device is not None, device

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length", 0) or 0)
            return self.rfile.read(min(length, 1_000_000)) if length else b""

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/icon.png":
                return self._send(200, icon, "image/png")
            if path == "/manifest.webmanifest":
                return self._send(200, MANIFEST, "application/manifest+json")
            ok, device = self._gate(path)
            if device is None and not ok:
                if is_allowed_client(self._client()):
                    if path.startswith("/api/"):
                        return self._json({"ok": False, "error": "unregistered"}, 401)
                    return self._html(build_register_page())
                return None
            if path == "/":
                latest = core.latest_report()
                body = latest.read_text(encoding="utf-8") if latest else None
                return self._html(
                    build_report_page(
                        body, latest.name if latest else None, bool(device.get("dev"))
                    )
                )
            if path == "/api/status":
                return self._json(core.status())
            if path == "/api/config_prompt" and device.get("dev"):
                prompt, count = core.config_prompt()
                return self._json({"ok": True, "prompt": prompt, "unclassified_count": count})
            if path == "/config/rules" and device.get("dev"):
                return self._send(200, core.config_path.read_bytes(), "text/plain; charset=utf-8")
            return self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/register":
                if not is_allowed_client(self._client()):
                    return self._send(403, b"forbidden", "text/plain")
                form = parse_qs(self._read_body().decode("utf-8", "replace"))
                token, error = core.register(
                    form.get("passphrase", [""])[0],
                    form.get("name", [""])[0],
                    form.get("dev", [""])[0] == "1",
                )
                if token is None:
                    return self._html(build_register_page(error))
                return self._send(303, b"", "text/plain", {"Location": "/", "Set-Cookie": _cookie(token)})
            ok, device = self._gate(path)
            if not ok:
                if is_allowed_client(self._client()):
                    self._json({"ok": False, "error": "この端末は登録されていません。"}, 401)
                return None
            if path == "/api/run":
                trigger = (
                    "nightly"
                    if "trigger=nightly" in self.path and device["id"] == "local"
                    else "manual"
                )
                started = core.start_run(trigger)
                return self._json({**core.status(), "started": started})
            if path == "/actions/bulk_archive":
                if core.status().get("state") == "running":
                    return self._json(
                        {"ok": False, "error": "実行中のため、終わってからもう一度押してください。"}
                    )
                try:
                    payload = json.loads(self._read_body() or b"{}")
                except json.JSONDecodeError:
                    payload = {}
                report, targets = core.archive_targets(list(payload.get("message_ids") or []))
                if report is None or not targets:
                    return self._json({"ok": True, "count": 0, "failed_count": 0})
                succeeded, failed = archive(targets)
                core.mark_archived(report, succeeded)
                logger.info(
                    "一括既読・アーカイブ(%s): 成功%d件 / 失敗%d件",
                    device["name"],
                    len(succeeded),
                    len(failed),
                )
                return self._json(
                    {"ok": True, "count": len(succeeded), "failed_count": len(failed)}
                )
            return self._send(404, b"not found", "text/plain")

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            logger.debug("%s %s", self._client(), format % args)

    return Handler


def serve(
    core: WebCore,
    archive: Callable[[list[str]], tuple[list[str], list[str]]],
    host: str = "0.0.0.0",
    port: int = 8765,
) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(core, archive))
    logger.info("mail-triage web: http://%s:%d/", host, port)
    httpd.serve_forever()
