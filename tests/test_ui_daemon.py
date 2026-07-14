"""
Tests for the memoir UI background-server lifecycle (memoir.ui.daemon).

These exercise the pidfile bookkeeping and process-liveness logic directly,
using a throwaway subprocess as a stand-in for a real `memoir ui` server —
covering status and stop without needing the webapp bundle built.

Run with: pytest tests/test_ui_daemon.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from memoir.ui import daemon


@pytest.fixture
def pidfile_dir(tmp_path, monkeypatch):
    """Redirect the module's pidfile directory into a throwaway tmp_path
    so tests never touch a developer's real ~/.memoir/ui-servers/.
    """
    d = tmp_path / "ui-servers"
    monkeypatch.setattr(daemon, "PIDFILE_DIR", d)
    return d


def _spawn_dummy_process():
    """A throwaway long-lived process standing in for a real UI server —
    all we need is a real, killable pid.
    """
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def _write_fake_record(
    store: str, pid: int, url: str = "http://localhost:9/?store=x"
) -> Path:
    """Write a pidfile for `store`, resolved the same way status_one/stop_one
    resolve it internally, so lookups by the caller's own `store` string hit
    the same file.
    """
    resolved = str(Path(store).resolve())
    daemon.PIDFILE_DIR.mkdir(parents=True, exist_ok=True)
    pidfile = daemon._pidfile_for(resolved)
    pidfile.write_text(
        json.dumps(
            {
                "pid": pid,
                "port": 9,
                "url": url,
                "store": resolved,
                "started": "2024-01-01T00:00:00Z",
                "log": "/dev/null",
            }
        )
    )
    return pidfile


class TestStatus:
    def test_status_one_untracked(self, pidfile_dir, tmp_path):
        assert daemon.status_one(str(tmp_path / "untracked")) is None

    def test_status_one_running(self, pidfile_dir, tmp_path):
        store = tmp_path / "store-a"
        proc = _spawn_dummy_process()
        try:
            _write_fake_record(str(store), proc.pid)
            result = daemon.status_one(str(store))
            assert result is not None
            assert result["state"] == "running"
            assert result["pid"] == proc.pid
        finally:
            proc.kill()
            proc.wait()

    def test_status_one_stale_when_process_exited(self, pidfile_dir, tmp_path):
        store = tmp_path / "store-b"
        proc = _spawn_dummy_process()
        proc.kill()
        proc.wait()
        _write_fake_record(str(store), proc.pid)
        result = daemon.status_one(str(store))
        assert result is not None
        assert result["state"] == "stale"

    def test_status_one_stale_when_no_url_recorded(self, pidfile_dir, tmp_path):
        # A launch that never reached ready state has a pid but no url.
        store = tmp_path / "store-c"
        proc = _spawn_dummy_process()
        try:
            daemon.PIDFILE_DIR.mkdir(parents=True, exist_ok=True)
            resolved = str(store.resolve())
            pidfile = daemon._pidfile_for(resolved)
            pidfile.write_text(json.dumps({"pid": proc.pid, "store": resolved}))
            result = daemon.status_one(str(store))
            assert result["state"] == "stale"
        finally:
            proc.kill()
            proc.wait()

    def test_status_all_lists_every_tracked_store(self, pidfile_dir, tmp_path):
        store_d = tmp_path / "store-d"
        store_e = tmp_path / "store-e"
        proc = _spawn_dummy_process()
        try:
            _write_fake_record(str(store_d), proc.pid)
            _write_fake_record(str(store_e), proc.pid)
            results = daemon.status_all()
            assert {r["store"] for r in results} == {
                str(store_d.resolve()),
                str(store_e.resolve()),
            }
        finally:
            proc.kill()
            proc.wait()

    def test_status_all_empty_when_untracked(self, pidfile_dir):
        assert daemon.status_all() == []


class TestStop:
    def test_stop_one_untracked_is_noop(self, pidfile_dir, tmp_path):
        assert daemon.stop_one(str(tmp_path / "untracked")) is None

    def test_stop_one_terminates_running_process(self, pidfile_dir, tmp_path):
        store = tmp_path / "store-f"
        proc = _spawn_dummy_process()
        pidfile = _write_fake_record(str(store), proc.pid)
        result = daemon.stop_one(str(store))
        assert result["outcome"] == "stopped"
        assert result["pid"] == proc.pid
        proc.wait(timeout=5)
        assert not daemon._process_alive(proc.pid)
        assert not pidfile.exists()

    def test_stop_one_already_gone(self, pidfile_dir, tmp_path):
        store = tmp_path / "store-g"
        proc = _spawn_dummy_process()
        proc.kill()
        proc.wait()
        pidfile = _write_fake_record(str(store), proc.pid)
        result = daemon.stop_one(str(store))
        assert result["outcome"] == "already gone"
        assert not pidfile.exists()

    def test_stop_all_stops_every_tracked_store(self, pidfile_dir, tmp_path):
        store_h = tmp_path / "store-h"
        store_i = tmp_path / "store-i"
        proc1 = _spawn_dummy_process()
        proc2 = _spawn_dummy_process()
        _write_fake_record(str(store_h), proc1.pid)
        _write_fake_record(str(store_i), proc2.pid)
        results = daemon.stop_all()
        assert {r["outcome"] for r in results} == {"stopped"}
        proc1.wait(timeout=5)
        proc2.wait(timeout=5)

    def test_stop_all_empty_when_untracked(self, pidfile_dir):
        assert daemon.stop_all() == []


class TestPidfileKeying:
    def test_same_store_maps_to_same_pidfile(self):
        assert daemon._pidfile_for("/a/b/c") == daemon._pidfile_for("/a/b/c")

    def test_different_stores_map_to_different_pidfiles(self):
        assert daemon._pidfile_for("/a/b/c") != daemon._pidfile_for("/a/b/d")
