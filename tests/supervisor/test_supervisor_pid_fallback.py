"""Tests for supervisor stale-PID detection and cmdline fallback in get_status_rows().

Covers:
  - _find_pid_by_cmdline: finds matching process, prefers real interpreter over shim
  - get_status_rows: uses cmdline fallback when PID file is stale/dead
  - get_status_rows: repairs stale PID file when fallback succeeds
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.supervisor.daemon import _find_pid_by_cmdline, get_status_rows


# ---------------------------------------------------------------------------
# _find_pid_by_cmdline
# ---------------------------------------------------------------------------

class TestFindPidByCmdline:
    def _make_proc(self, pid: int, name: str, cmdline: list[str], rss: int = 50_000_000):
        p = MagicMock()
        p.pid = pid
        p.name.return_value = name
        p.cmdline.return_value = cmdline
        p.memory_info.return_value = MagicMock(rss=rss)
        return p

    def test_finds_matching_process(self):
        proc = self._make_proc(1234, "python.exe", ["python.exe", "tracker.py"])
        with patch("src.supervisor.daemon.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = [proc]
            mock_psutil.NoSuchProcess = Exception
            mock_psutil.AccessDenied = Exception
            result = _find_pid_by_cmdline("tracker.py")
        assert result == 1234

    def test_prefers_high_rss_real_interpreter_over_shim(self):
        shim = self._make_proc(100, "python.exe", ["C:/venv/Scripts/python.exe", "tracker.py"], rss=0)
        real = self._make_proc(200, "python.exe", ["C:/Python310/python.exe", "tracker.py"], rss=50_000_000)
        with patch("src.supervisor.daemon.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = [shim, real]
            mock_psutil.NoSuchProcess = Exception
            mock_psutil.AccessDenied = Exception
            result = _find_pid_by_cmdline("tracker.py")
        assert result == 200  # real interpreter has higher RSS

    def test_returns_none_when_no_match(self):
        proc = self._make_proc(999, "python.exe", ["python.exe", "other_script.py"])
        with patch("src.supervisor.daemon.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = [proc]
            mock_psutil.NoSuchProcess = Exception
            mock_psutil.AccessDenied = Exception
            result = _find_pid_by_cmdline("tracker.py")
        assert result is None

    def test_skips_non_python_processes(self):
        non_py = self._make_proc(555, "notepad.exe", ["notepad.exe", "tracker.py"])
        with patch("src.supervisor.daemon.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = [non_py]
            mock_psutil.NoSuchProcess = Exception
            mock_psutil.AccessDenied = Exception
            result = _find_pid_by_cmdline("tracker.py")
        assert result is None


# ---------------------------------------------------------------------------
# get_status_rows — stale PID fallback
# ---------------------------------------------------------------------------

class TestGetStatusRowsStalePID:
    def _stale_pid_scenario(self, stale_pid: int, real_pid: int, log_age_s: float = 30.0):
        """Set up mocks for a component whose PID file has stale_pid but real process is real_pid."""
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # Create stale PID file
            pid_file = tmp / "tracker.pid"
            pid_file.write_text(str(stale_pid))

            # Create log file with recent mtime
            log_file = tmp / "tracker.log"
            log_file.write_text("heartbeat\n")
            os.utime(log_file, (time.time() - log_age_s, time.time() - log_age_s))

            mock_proc = MagicMock()
            mock_proc.pid = real_pid
            mock_proc.name.return_value = "python.exe"
            mock_proc.cmdline.return_value = ["python.exe", "ginarea_tracker/tracker.py"]
            mock_proc.memory_info.return_value = MagicMock(rss=50_000_000)

            with (
                patch("src.supervisor.daemon.RUN_DIR", tmp),
                patch("src.supervisor.daemon.CURRENT_DIR", tmp),
                patch("src.supervisor.daemon.DAEMON_PID_PATH", tmp / "supervisor.pid"),
                patch("src.supervisor.daemon._WATCHDOG_PID_PATH", tmp / "watchdog.pid"),
                patch("src.supervisor.daemon.pid_path", return_value=pid_file),
                patch("src.supervisor.daemon.log_path", return_value=log_file),
                patch("src.supervisor.daemon._pid_alive", return_value=False),
                patch("src.supervisor.daemon._pid_alive_for", return_value=False),
                patch("src.supervisor.daemon.psutil") as mock_psutil,
                patch("src.supervisor.daemon.ALL_COMPONENTS", ["tracker"]),
                patch("src.supervisor.daemon.COMPONENTS", {
                    "tracker": {
                        "cmdline_must_contain": "tracker.py",
                        "health_stale_min": 15,
                        "log": "tracker.log",
                    }
                }),
            ):
                mock_psutil.NoSuchProcess = Exception
                mock_psutil.AccessDenied = Exception
                mock_psutil.process_iter.return_value = [mock_proc]

                rows = get_status_rows()

                # PID file should be repaired
                repaired_pid = pid_file.read_text().strip()
                return rows, repaired_pid

    def test_stale_pid_shows_ok_via_cmdline_fallback(self):
        rows, _ = self._stale_pid_scenario(stale_pid=99999, real_pid=10376, log_age_s=30)
        tracker_row = next(r for r in rows if r["component"] == "tracker")
        assert tracker_row["health"] == "OK", f"Expected OK, got {tracker_row['health']}"
        assert tracker_row["pid"] == 10376

    def test_stale_pid_file_is_repaired(self):
        _, repaired = self._stale_pid_scenario(stale_pid=99999, real_pid=10376)
        assert repaired == "10376", f"PID file not repaired: got {repaired}"

    def test_truly_dead_process_still_shows_dead(self):
        import time
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            pid_file = tmp / "tracker.pid"
            pid_file.write_text("99999")
            log_file = tmp / "tracker.log"
            log_file.write_text("old log\n")

            with (
                patch("src.supervisor.daemon.RUN_DIR", tmp),
                patch("src.supervisor.daemon.CURRENT_DIR", tmp),
                patch("src.supervisor.daemon.DAEMON_PID_PATH", tmp / "supervisor.pid"),
                patch("src.supervisor.daemon._WATCHDOG_PID_PATH", tmp / "watchdog.pid"),
                patch("src.supervisor.daemon.pid_path", return_value=pid_file),
                patch("src.supervisor.daemon.log_path", return_value=log_file),
                patch("src.supervisor.daemon._pid_alive", return_value=False),
                patch("src.supervisor.daemon._pid_alive_for", return_value=False),
                patch("src.supervisor.daemon.psutil") as mock_psutil,
                patch("src.supervisor.daemon.ALL_COMPONENTS", ["tracker"]),
                patch("src.supervisor.daemon.COMPONENTS", {
                    "tracker": {
                        "cmdline_must_contain": "tracker.py",
                        "health_stale_min": 15,
                        "log": "tracker.log",
                    }
                }),
            ):
                mock_psutil.NoSuchProcess = Exception
                mock_psutil.AccessDenied = Exception
                mock_psutil.process_iter.return_value = []  # no matching process

                rows = get_status_rows()

            tracker_row = next(r for r in rows if r["component"] == "tracker")
            assert tracker_row["health"] == "DEAD"
