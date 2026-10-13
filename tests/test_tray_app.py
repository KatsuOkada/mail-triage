import os

from mail_triage import tray_app
from mail_triage.tray_app import _ensure_single_instance, _toggle_config_flag


def test_toggle_flips_true_to_false(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text('{\n  "dry_run": true,\n  "jev_enabled": false\n}\n', encoding="utf-8")

    new_value = _toggle_config_flag(config_path, "dry_run")

    assert new_value is False
    assert '"dry_run": false' in config_path.read_text(encoding="utf-8")


def test_toggle_flips_false_to_true(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text('{\n  "jev_enabled": false\n}\n', encoding="utf-8")

    new_value = _toggle_config_flag(config_path, "jev_enabled")

    assert new_value is True
    assert '"jev_enabled": true' in config_path.read_text(encoding="utf-8")


def test_toggle_preserves_surrounding_formatting(tmp_path):
    config_path = tmp_path / "config.json"
    original = (
        '{\n'
        '  "dry_run": true,\n'
        '\n'
        '  "sender_categories": [\n'
        '    {"category": "EC", "domain_regex": "example\\\\.com$"}\n'
        '  ]\n'
        '}\n'
    )
    config_path.write_text(original, encoding="utf-8")

    _toggle_config_flag(config_path, "dry_run")

    updated = config_path.read_text(encoding="utf-8")
    assert updated == original.replace('"dry_run": true', '"dry_run": false')


def test_toggle_only_affects_named_key(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text('{\n  "dry_run": true,\n  "jev_enabled": true\n}\n', encoding="utf-8")

    _toggle_config_flag(config_path, "dry_run")

    text = config_path.read_text(encoding="utf-8")
    assert '"dry_run": false' in text
    assert '"jev_enabled": true' in text


def test_ensure_single_instance_creates_lock_when_none_exists(tmp_path, monkeypatch):
    lock_path = tmp_path / "tray.lock"

    def fail_if_called(*args, **kwargs):
        raise AssertionError("no existing lock file, should not check/kill any process")

    monkeypatch.setattr(tray_app.subprocess, "run", fail_if_called)

    _ensure_single_instance(lock_path)

    assert lock_path.read_text(encoding="utf-8") == str(os.getpid())


def test_ensure_single_instance_kills_stale_running_pid(tmp_path, monkeypatch):
    lock_path = tmp_path / "tray.lock"
    lock_path.write_text("99999", encoding="utf-8")
    monkeypatch.setattr(tray_app, "_is_process_running", lambda pid: True)

    calls = []
    monkeypatch.setattr(
        tray_app.subprocess, "run", lambda *a, **kw: calls.append(a) or None
    )

    _ensure_single_instance(lock_path)

    assert calls == [(["taskkill", "/PID", "99999", "/F"],)]
    assert lock_path.read_text(encoding="utf-8") == str(os.getpid())


def test_ensure_single_instance_skips_kill_when_pid_not_running(tmp_path, monkeypatch):
    lock_path = tmp_path / "tray.lock"
    lock_path.write_text("99999", encoding="utf-8")
    monkeypatch.setattr(tray_app, "_is_process_running", lambda pid: False)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("pid is not running, should not attempt to kill it")

    monkeypatch.setattr(tray_app.subprocess, "run", fail_if_called)

    _ensure_single_instance(lock_path)

    assert lock_path.read_text(encoding="utf-8") == str(os.getpid())
