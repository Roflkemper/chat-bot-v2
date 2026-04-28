"""TZ-045: Orphan kill + memory alarm tests for supervisor daemon."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


# ─────────────────────────────────────────────────────────────────────────────
# _kill_process_tree
# ─────────────────────────────────────────────────────────────────────────────

class TestKillProcessTree:
    def test_terminates_parent_and_children(self):
        import psutil
        from src.supervisor.daemon import _kill_process_tree

        mock_parent = MagicMock()
        mock_child1 = MagicMock()
        mock_child2 = MagicMock()
        mock_parent.children.return_value = [mock_child1, mock_child2]

        with patch("src.supervisor.daemon.psutil") as mock_ps:
            mock_ps.Process.return_value = mock_parent
            mock_ps.wait_procs.return_value = ([], [])
            mock_ps.NoSuchProcess = psutil.NoSuchProcess
            mock_ps.AccessDenied = psutil.AccessDenied
            _kill_process_tree(1234, "test_component", timeout=1)

        mock_child1.terminate.assert_called_once()
        mock_child2.terminate.assert_called_once()
        mock_parent.terminate.assert_called_once()

    def test_sigkill_survivors(self):
        import psutil
        from src.supervisor.daemon import _kill_process_tree

        mock_parent = MagicMock()
        mock_parent.children.return_value = []

        with patch("src.supervisor.daemon.psutil") as mock_ps:
            mock_ps.Process.return_value = mock_parent
            mock_ps.wait_procs.return_value = ([], [mock_parent])
            mock_ps.NoSuchProcess = psutil.NoSuchProcess
            _kill_process_tree(1234, "test_component", timeout=1)

        mock_parent.kill.assert_called_once()

    def test_no_such_process_is_silently_ignored(self):
        import psutil
        from src.supervisor.daemon import _kill_process_tree

        with patch("src.supervisor.daemon.psutil") as mock_ps:
            mock_ps.Process.side_effect = psutil.NoSuchProcess(9999)
            mock_ps.NoSuchProcess = psutil.NoSuchProcess
            # Must not raise
            _kill_process_tree(9999, "test_component", timeout=1)

    def test_none_psutil_uses_os_kill_fallback(self):
        from src.supervisor.daemon import _kill_process_tree

        with patch("src.supervisor.daemon.psutil", None):
            with patch("os.kill") as mock_kill:
                # Make the loop exit immediately (process gone after first check)
                mock_kill.side_effect = [None, OSError("no such process")]
                _kill_process_tree(1234, "test_component", timeout=1)

        # SIGTERM sent
        mock_kill.assert_any_call(1234, __import__("signal").SIGTERM)


# ─────────────────────────────────────────────────────────────────────────────
# _kill_cmdline_matching
# ─────────────────────────────────────────────────────────────────────────────

class TestKillCmdlineMatching:
    def _make_proc(self, pid: int, cmdline: str, pname: str = "python.exe") -> MagicMock:
        m = MagicMock()
        m.pid = pid
        m.name.return_value = pname
        m.cmdline.return_value = cmdline.split()
        m.is_running.return_value = False
        return m

    def test_kills_matching_python_processes(self):
        import psutil
        from src.supervisor.daemon import _kill_cmdline_matching

        proc_match = self._make_proc(1111, "python app_runner.py")
        proc_other = self._make_proc(2222, "python tracker.py")

        with patch("src.supervisor.daemon.psutil") as mock_ps:
            mock_ps.process_iter.return_value = [proc_match, proc_other]
            mock_ps.NoSuchProcess = psutil.NoSuchProcess
            mock_ps.AccessDenied = psutil.AccessDenied
            survivor = MagicMock()
            survivor.is_running.return_value = False
            mock_ps.Process.return_value = survivor
            with patch("time.sleep"):
                _kill_cmdline_matching("app_runner.py", "app_runner")

        proc_match.terminate.assert_called_once()
        proc_other.terminate.assert_not_called()

    def test_does_not_kill_supervisor_itself(self):
        import psutil
        from src.supervisor.daemon import _kill_cmdline_matching

        own_pid = os.getpid()
        proc_self = self._make_proc(own_pid, "python app_runner.py")
        proc_other = self._make_proc(9999, "python app_runner.py")

        with patch("src.supervisor.daemon.psutil") as mock_ps:
            mock_ps.process_iter.return_value = [proc_self, proc_other]
            mock_ps.NoSuchProcess = psutil.NoSuchProcess
            mock_ps.AccessDenied = psutil.AccessDenied
            survivor = MagicMock()
            survivor.is_running.return_value = False
            mock_ps.Process.return_value = survivor
            with patch("time.sleep"):
                _kill_cmdline_matching("app_runner.py", "app_runner")

        proc_self.terminate.assert_not_called()
        proc_other.terminate.assert_called_once()

    def test_no_match_no_kill(self):
        import psutil
        from src.supervisor.daemon import _kill_cmdline_matching

        proc = self._make_proc(5555, "python tracker.py")

        with patch("src.supervisor.daemon.psutil") as mock_ps:
            mock_ps.process_iter.return_value = [proc]
            mock_ps.NoSuchProcess = psutil.NoSuchProcess
            mock_ps.AccessDenied = psutil.AccessDenied
            _kill_cmdline_matching("app_runner.py", "app_runner")

        proc.terminate.assert_not_called()

    def test_non_python_process_skipped(self):
        import psutil
        from src.supervisor.daemon import _kill_cmdline_matching

        proc = self._make_proc(6666, "python app_runner.py", pname="node.exe")

        with patch("src.supervisor.daemon.psutil") as mock_ps:
            mock_ps.process_iter.return_value = [proc]
            mock_ps.NoSuchProcess = psutil.NoSuchProcess
            mock_ps.AccessDenied = psutil.AccessDenied
            _kill_cmdline_matching("app_runner.py", "app_runner")

        proc.terminate.assert_not_called()

    def test_none_psutil_returns_early(self):
        from src.supervisor.daemon import _kill_cmdline_matching

        with patch("src.supervisor.daemon.psutil", None):
            # Must not raise, must not call anything
            _kill_cmdline_matching("app_runner.py", "app_runner")


# ─────────────────────────────────────────────────────────────────────────────
# ManagedProcess.start() — calls _kill_cmdline_matching before launch
# ─────────────────────────────────────────────────────────────────────────────

class TestManagedProcessStartKillsOrphans:
    def _make_mp(self, fragment: str = "app_runner.py"):
        from src.supervisor.daemon import ManagedProcess
        from src.supervisor.process_config import COMPONENTS
        cfg = dict(COMPONENTS["app_runner"])
        cfg["cmdline_must_contain"] = fragment
        return ManagedProcess("app_runner", cfg)

    def test_start_calls_kill_cmdline_matching(self):
        mp = self._make_mp()
        mock_proc = MagicMock()
        mock_proc.pid = 42

        with patch("src.supervisor.daemon._kill_cmdline_matching") as mock_kill:
            with patch("subprocess.Popen", return_value=mock_proc):
                with patch.object(Path, "write_text"):
                    with patch.object(Path, "mkdir"):
                        with patch("builtins.open", MagicMock()):
                            mp.start()

        mock_kill.assert_called_once_with("app_runner.py", "app_runner")

    def test_start_no_fragment_skips_kill(self):
        from src.supervisor.daemon import ManagedProcess
        from src.supervisor.process_config import COMPONENTS
        cfg = dict(COMPONENTS["tracker"])
        cfg.pop("cmdline_must_contain", None)
        mp = ManagedProcess("tracker", cfg)

        mock_proc = MagicMock()
        mock_proc.pid = 99

        with patch("src.supervisor.daemon._kill_cmdline_matching") as mock_kill:
            with patch("subprocess.Popen", return_value=mock_proc):
                with patch.object(Path, "write_text"):
                    with patch.object(Path, "mkdir"):
                        with patch("builtins.open", MagicMock()):
                            mp.start()

        mock_kill.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# ManagedProcess.stop() — tree-kill + cmdline sweep
# ─────────────────────────────────────────────────────────────────────────────

class TestManagedProcessStopTreeKill:
    def _make_started_mp(self):
        from src.supervisor.daemon import ManagedProcess
        from src.supervisor.process_config import COMPONENTS
        cfg = dict(COMPONENTS["app_runner"])
        cfg["cmdline_must_contain"] = "app_runner.py"
        mp = ManagedProcess("app_runner", cfg)
        mp.proc = MagicMock()
        mp.proc.pid = 42
        mp.proc.poll.return_value = None
        return mp

    def test_stop_calls_tree_kill_and_cmdline_sweep(self):
        mp = self._make_started_mp()

        with patch("src.supervisor.daemon._kill_process_tree") as mock_tree:
            with patch("src.supervisor.daemon._kill_cmdline_matching") as mock_cmdline:
                with patch.object(Path, "exists", return_value=False):
                    mp.stop(timeout=1)

        mock_tree.assert_called_once_with(42, "app_runner", timeout=1)
        mock_cmdline.assert_called_once_with("app_runner.py", "app_runner")

    def test_stop_clears_proc_and_pid_file(self, tmp_path):
        mp = self._make_started_mp()
        pid_file = tmp_path / "app_runner.pid"
        pid_file.write_text("42")

        with patch("src.supervisor.daemon._kill_process_tree"):
            with patch("src.supervisor.daemon._kill_cmdline_matching"):
                with patch("src.supervisor.daemon.pid_path", return_value=pid_file):
                    mp.stop(timeout=1)

        assert mp.proc is None
        assert not pid_file.exists()


# ─────────────────────────────────────────────────────────────────────────────
# Memory snapshot thread
# ─────────────────────────────────────────────────────────────────────────────

class TestMemorySnapshotThread:
    def _make_procs(self, pid: int = 1234, name: str = "app_runner"):
        from src.supervisor.daemon import ManagedProcess
        from src.supervisor.process_config import COMPONENTS
        mp = ManagedProcess(name, COMPONENTS[name])
        mock_proc = MagicMock()
        mock_proc.pid = pid
        mock_proc.poll.return_value = None
        mp.proc = mock_proc
        return {name: mp}

    def _mock_shim(self, rss_bytes: int, child_pid: int | None = None, child_rss: int | None = None):
        """Build a mock psutil.Process (shim) optionally with one child."""
        import psutil as _psutil
        shim = MagicMock()
        shim.pid = 1234
        shim.memory_info.return_value.rss = rss_bytes
        if child_pid is not None:
            child = MagicMock()
            child.pid = child_pid
            child.memory_info.return_value.rss = child_rss or rss_bytes
            shim.children.return_value = [child]
        else:
            shim.children.return_value = []
        return shim

    def _run_thread(self, procs, mock_ps, tmp_path, extra_patches=()):
        import psutil as _psutil
        from src.supervisor.daemon import _memory_snapshot_thread
        stop = threading.Event()
        mock_ps.NoSuchProcess = _psutil.NoSuchProcess
        mock_ps.AccessDenied = _psutil.AccessDenied

        ctx = [
            patch("src.supervisor.daemon.CURRENT_DIR", tmp_path),
            patch("src.supervisor.daemon._MEMORY_SNAPSHOT_INTERVAL", 0),
        ]
        for p in extra_patches:
            ctx.append(p)

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in ctx:
                stack.enter_context(p)
            t = threading.Thread(target=_memory_snapshot_thread, args=(procs, stop))
            t.start()
            time.sleep(0.15)
            stop.set()
            t.join(timeout=3)

    def test_logs_rss_to_memory_log(self, tmp_path):
        procs = self._make_procs()
        shim = self._mock_shim(100 * 1024 * 1024)

        with patch("src.supervisor.daemon.psutil") as mock_ps:
            mock_ps.Process.return_value = shim
            self._run_thread(procs, mock_ps, tmp_path)

        mem_log = tmp_path / "memory.log"
        assert mem_log.exists()
        content = mem_log.read_text()
        assert "app_runner" in content
        assert "RSS=100.0MB" in content

    def test_tracks_grandchild_not_shim(self, tmp_path):
        """Real interpreter child RSS is reported, not the shim's tiny RSS."""
        procs = self._make_procs()
        # shim = 4 MB, child (real interpreter) = 200 MB
        shim = self._mock_shim(4 * 1024 * 1024, child_pid=9999, child_rss=200 * 1024 * 1024)

        with patch("src.supervisor.daemon.psutil") as mock_ps:
            mock_ps.Process.return_value = shim
            self._run_thread(procs, mock_ps, tmp_path)

        content = (tmp_path / "memory.log").read_text()
        assert "RSS=200.0MB" in content
        assert "9999" in content  # real PID logged

    def test_alarm_sent_at_500mb(self, tmp_path):
        procs = self._make_procs()
        shim = self._mock_shim(600 * 1024 * 1024)

        with patch("src.supervisor.daemon.psutil") as mock_ps:
            mock_ps.Process.return_value = shim
            with patch("src.supervisor.daemon._send_telegram_alarm") as mock_alarm:
                self._run_thread(procs, mock_ps, tmp_path,
                                 extra_patches=[patch("src.supervisor.daemon._send_telegram_alarm", mock_alarm)])

        mock_alarm.assert_called()
        assert "MEMORY ALARM" in mock_alarm.call_args[0][0]
        assert "app_runner" in mock_alarm.call_args[0][0]

    def test_autorestart_at_800mb_app_runner(self, tmp_path):
        """At >= 800 MB for app_runner: CRITICAL alarm + mp.stop() called."""
        procs = self._make_procs()
        shim = self._mock_shim(850 * 1024 * 1024)
        mp = procs["app_runner"]

        def _side_stop():
            mp.proc = None  # simulate real stop() clearing proc so loop exits

        with patch("src.supervisor.daemon.psutil") as mock_ps:
            mock_ps.Process.return_value = shim
            with patch("src.supervisor.daemon._send_telegram_alarm") as mock_alarm:
                with patch.object(mp, "stop", side_effect=_side_stop) as mock_stop:
                    self._run_thread(procs, mock_ps, tmp_path,
                                     extra_patches=[
                                         patch("src.supervisor.daemon._send_telegram_alarm", mock_alarm),
                                     ])

        mock_alarm.assert_called()
        assert "MEMORY CRITICAL" in mock_alarm.call_args_list[0][0][0]
        mock_stop.assert_called_once()

    def test_no_autorestart_at_800mb_non_app_runner(self, tmp_path):
        """At >= 800 MB for tracker: ALARM only, no auto-restart."""
        procs = self._make_procs(name="tracker")
        shim = self._mock_shim(850 * 1024 * 1024)
        mp = procs["tracker"]

        with patch("src.supervisor.daemon.psutil") as mock_ps:
            mock_ps.Process.return_value = shim
            with patch("src.supervisor.daemon._send_telegram_alarm") as mock_alarm:
                with patch.object(mp, "stop") as mock_stop:
                    self._run_thread(procs, mock_ps, tmp_path,
                                     extra_patches=[
                                         patch("src.supervisor.daemon._send_telegram_alarm", mock_alarm),
                                     ])

        mock_alarm.assert_called()
        assert "MEMORY ALARM" in mock_alarm.call_args[0][0]
        mock_stop.assert_not_called()

    def test_no_alarm_below_300mb(self, tmp_path):
        procs = self._make_procs()
        shim = self._mock_shim(100 * 1024 * 1024)

        with patch("src.supervisor.daemon.psutil") as mock_ps:
            mock_ps.Process.return_value = shim
            with patch("src.supervisor.daemon._send_telegram_alarm") as mock_alarm:
                self._run_thread(procs, mock_ps, tmp_path,
                                 extra_patches=[patch("src.supervisor.daemon._send_telegram_alarm", mock_alarm)])

        mock_alarm.assert_not_called()

    def test_disabled_when_psutil_none(self, tmp_path):
        from src.supervisor.daemon import _memory_snapshot_thread

        procs = self._make_procs()
        stop = threading.Event()

        with patch("src.supervisor.daemon.psutil", None):
            with patch("src.supervisor.daemon.CURRENT_DIR", tmp_path):
                t = threading.Thread(target=_memory_snapshot_thread, args=(procs, stop))
                t.start()
                t.join(timeout=2)

        assert not (tmp_path / "memory.log").exists()
