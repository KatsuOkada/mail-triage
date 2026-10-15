import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from mail_triage import web_app
from mail_triage.web_app import WebCore, build_report_page, is_allowed_client, make_handler

REPORT = """<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><title>t</title></head>
<body><h1>結果</h1><button id="bulk-archive-btn"></button><button id="config-btn"></button>
<script>const NO_CHECK_IDS = ["a", "b", "c"];</script></body></html>"""


@pytest.fixture
def core(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    gate = threading.Event()
    calls = []

    def runner(progress):
        progress("メールの取得")
        calls.append(1)
        gate.wait(5)
        (log_dir / "2026-10-15_090000_report.html").write_text(REPORT, encoding="utf-8")

    c = WebCore(tmp_path, log_dir, tmp_path / "rules.json", runner)
    c.gate, c.calls = gate, calls
    c.set_passphrase("secret-word")
    return c


def _wait(cond, timeout=3):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


@pytest.mark.parametrize(
    "ip,ok",
    [
        ("192.168.10.50", True),
        ("10.0.0.3", True),
        ("127.0.0.1", True),
        ("::ffff:192.168.10.9", True),
        ("8.8.8.8", False),
        ("2001:db8::5", False),
        ("bad", False),
    ],
)
def test_is_allowed_client_only_lan_ipv4_and_loopback(ip, ok):  # R-17, F-1
    assert is_allowed_client(ip) is ok


def test_register_with_correct_passphrase_then_device_is_found(core):  # R-12, F-3, F-2
    token, error = core.register("secret-word", "iPad", is_dev=False)
    assert error == ""
    device = core.find_device(token)
    assert device["name"] == "iPad" and device["dev"] is False
    assert core.find_device("other-token") is None
    assert token not in json.dumps(core.devices())  # トークンそのものは保存しない


def test_wrong_passphrase_locks_out_after_five_failures(core):  # R-14
    for _ in range(4):
        assert core.register("wrong", "x", False) == (None, "合言葉が違います。")
    token, error = core.register("wrong", "x", False)
    assert token is None and "15分" in error
    token, error = core.register("secret-word", "x", False)  # 正しくても待ち時間中は断る
    assert token is None and "待って" in error


def test_revoke_removes_device(core):  # Q-4, F-14
    token, _ = core.register("secret-word", "phone", False)
    device_id = core.find_device(token)["id"]
    assert core.revoke(device_id) is True
    assert core.find_device(token) is None


def test_run_joins_when_already_running(core):  # R-5, R-8, F-5
    assert core.start_run("manual") is True
    assert _wait(lambda: core.status()["stage"] == "メールの取得")
    assert core.start_run("manual") is False  # 相乗り
    core.gate.set()
    assert _wait(lambda: core.status()["state"] == "succeeded")
    assert core.calls == [1]
    assert core.status()["report"] == "2026-10-15_090000_report.html"


def test_failed_run_keeps_previous_report_and_reports_error(tmp_path):  # R-11
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "2026-10-14_210000_report.html").write_text(REPORT, encoding="utf-8")

    def runner(progress):
        raise RuntimeError("Gmail に接続できません")

    c = WebCore(tmp_path, log_dir, tmp_path / "rules.json", runner)
    c.start_run("manual")
    assert _wait(lambda: c.status()["state"] == "failed")
    s = c.status()
    assert "Gmail に接続できません" in s["error"]
    assert s["report"] == "2026-10-14_210000_report.html"


def test_running_state_left_by_crash_becomes_failed(tmp_path):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "run_state.json").write_text('{"state": "running"}', encoding="utf-8")
    c = WebCore(tmp_path, tmp_path, tmp_path / "rules.json", lambda p: None)
    assert c.status()["state"] == "failed"


def test_archive_targets_only_latest_report_and_not_yet_archived(core):  # R-9, R-10, F-9
    (core.log_dir / "2026-10-15_090000_report.html").write_text(REPORT, encoding="utf-8")
    report, targets = core.archive_targets(["a", "b", "zzz"])
    assert targets == ["a", "b"]
    core.mark_archived(report, ["a"])
    assert core.archive_targets(["a", "b", "c"])[1] == ["b", "c"]


def test_report_page_hides_dev_buttons_for_other_devices():  # R-15, Q-1
    page = build_report_page(REPORT, "r.html", is_dev=False)
    assert "#config-btn, #open-config-btn { display: none; }" in page
    assert 'id="mt-run-btn"' in page and "viewport" in page
    dev_page = build_report_page(REPORT, "r.html", is_dev=True)
    assert "display: none; }</style>" not in dev_page.split("</head>")[0].split("mt-fail")[-1]
    assert "launchClaudeConfig = async function" in dev_page


def test_report_page_without_report_says_no_result():  # R-4
    assert "まだ結果がありません" in build_report_page(None, None, is_dev=False)


@pytest.fixture
def server(core, monkeypatch):
    archived = []
    monkeypatch.setattr(
        web_app, "is_loopback", lambda ip: False
    )  # テストでは 127.0.0.1 を LAN の端末として扱う
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0), make_handler(core, lambda ids: (archived.extend(ids) or ids, []))
    )
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", archived
    core.gate.set()
    httpd.shutdown()


def _request(url, data=None, cookie=None, method=None):
    req = urllib.request.Request(url, data=data, method=method)
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, res.read().decode("utf-8"), res.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), e.headers


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _register(base):
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(f"{base}/register", data=b"passphrase=secret-word&name=phone")
    except urllib.error.HTTPError as e:
        assert e.code == 303
        return e.headers["Set-Cookie"].split(";")[0]
    raise AssertionError("登録で 303 が返らない")


def test_unregistered_device_sees_only_register_page(server, core):  # R-13, UC-6
    base, _ = server
    (core.log_dir / "2026-10-15_090000_report.html").write_text(REPORT, encoding="utf-8")
    status, body, _ = _request(base + "/")
    assert status == 200 and "合言葉" in body and "結果" not in body
    assert _request(base + "/api/status")[0] == 401
    assert _request(base + "/api/run", data=b"", method="POST")[0] == 401
    assert (
        _request(base + "/actions/bulk_archive", data=b'{"message_ids":["a"]}', method="POST")[0]
        == 401
    )


def test_registered_device_can_view_run_and_archive(server, core):  # R-1, R-5, R-9, UC-1〜3
    base, archived = server
    (core.log_dir / "2026-10-15_090000_report.html").write_text(REPORT, encoding="utf-8")
    cookie = _register(base)
    status, body, _ = _request(base + "/", cookie=cookie)
    assert status == 200 and "<h1>結果</h1>" in body and "今すぐ実行" in body
    status, body, _ = _request(
        base + "/actions/bulk_archive",
        data=b'{"message_ids":["a","b"]}',
        cookie=cookie,
        method="POST",
    )
    assert json.loads(body) == {"ok": True, "count": 2, "failed_count": 0} and archived == [
        "a",
        "b",
    ]
    status, body, _ = _request(
        base + "/actions/bulk_archive",
        data=b'{"message_ids":["a","b"]}',
        cookie=cookie,
        method="POST",
    )
    assert json.loads(body)["count"] == 0  # 別の端末ですでにアーカイブ済み
    status, body, _ = _request(base + "/api/run", data=b"", cookie=cookie, method="POST")
    assert json.loads(body)["started"] is True
    status, body, _ = _request(
        base + "/actions/bulk_archive", data=b'{"message_ids":["c"]}', cookie=cookie, method="POST"
    )
    assert json.loads(body)["ok"] is False  # 実行中は断る


def test_dev_only_endpoints_refused_for_normal_device(server):  # R-15
    base, _ = server
    cookie = _register(base)
    assert _request(base + "/api/config_prompt", cookie=cookie)[0] == 404
    assert _request(base + "/config/rules", cookie=cookie)[0] == 404
