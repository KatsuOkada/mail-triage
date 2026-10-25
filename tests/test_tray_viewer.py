import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import tray_viewer  # noqa: E402


def test_load_url_reads_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("MAIL_TRIAGE_WEB_URL", raising=False)
    env = tmp_path / ".env"
    env.write_text('OTHER=1\nMAIL_TRIAGE_WEB_URL="http://192.0.2.10:8765/"\n', encoding="utf-8")
    assert tray_viewer.load_url(env) == "http://192.0.2.10:8765/"


def test_load_url_rejects_non_http_and_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("MAIL_TRIAGE_WEB_URL", raising=False)
    env = tmp_path / ".env"
    env.write_text("MAIL_TRIAGE_WEB_URL=file:///C:/x\n", encoding="utf-8")
    assert tray_viewer.load_url(env) is None
    assert tray_viewer.load_url(tmp_path / "none.env") is None


def test_open_view_uses_app_window(monkeypatch):
    calls = []
    monkeypatch.setattr(tray_viewer, "find_browser", lambda: "chrome.exe")
    monkeypatch.setattr(tray_viewer.subprocess, "Popen", lambda args, **kw: calls.append(args))
    tray_viewer.open_view("http://192.0.2.10:8765/")
    assert calls == [["chrome.exe", "--app=http://192.0.2.10:8765/"]]


def test_find_browser_prefers_chrome_over_edge(tmp_path, monkeypatch):
    monkeypatch.setattr(tray_viewer.shutil, "which", lambda name: None)
    monkeypatch.setattr(tray_viewer, "_PROGRAM_DIRS", [tmp_path])
    edge = tmp_path / "Microsoft/Edge/Application/msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.touch()
    assert tray_viewer.find_browser() == str(edge)
    chrome = tmp_path / "Google/Chrome/Application/chrome.exe"
    chrome.parent.mkdir(parents=True)
    chrome.touch()
    assert tray_viewer.find_browser() == str(chrome)


def test_open_view_falls_back_to_default_browser(monkeypatch):
    opened = []
    monkeypatch.setattr(tray_viewer, "find_browser", lambda: None)
    monkeypatch.setattr(tray_viewer.webbrowser, "open", opened.append)
    tray_viewer.open_view("http://192.0.2.10:8765/")
    assert opened == ["http://192.0.2.10:8765/"]
