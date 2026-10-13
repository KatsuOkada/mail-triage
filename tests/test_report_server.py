from pathlib import Path

from mail_triage import report_server
from mail_triage.report_server import open_in_editor


def _record_popen(monkeypatch):
    calls = []
    monkeypatch.setattr(report_server.subprocess, "Popen", lambda args, **kw: calls.append(args))
    return calls


def test_open_in_editor_uses_vscode_when_found(monkeypatch):
    calls = _record_popen(monkeypatch)
    monkeypatch.setattr(report_server, "_find_vscode", lambda: r"C:\vscode\code.cmd")

    editor = open_in_editor(Path("config.json"))

    assert editor == "VS Code"
    assert calls == [[r"C:\vscode\code.cmd", "config.json"]]


def test_open_in_editor_falls_back_to_notepad(monkeypatch):
    calls = _record_popen(monkeypatch)
    monkeypatch.setattr(report_server, "_find_vscode", lambda: None)

    editor = open_in_editor(Path("config.json"))

    assert editor == "メモ帳"
    assert calls == [["notepad.exe", "config.json"]]


def test_find_vscode_prefers_path_lookup(monkeypatch):
    monkeypatch.setattr(report_server.shutil, "which", lambda name: r"C:\bin\code.cmd")

    assert report_server._find_vscode() == r"C:\bin\code.cmd"


def test_find_vscode_uses_default_install_location(monkeypatch, tmp_path):
    bin_dir = tmp_path / "Programs" / "Microsoft VS Code" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "code.cmd").write_text("", encoding="utf-8")
    monkeypatch.setattr(report_server.shutil, "which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert report_server._find_vscode() == str(bin_dir / "code.cmd")


def test_find_vscode_returns_none_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(report_server.shutil, "which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert report_server._find_vscode() is None
