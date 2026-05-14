"""Cross-platform PID lock for collectors process."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def _process_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return exit_code.value == 259  # STILL_ACTIVE
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # process exists but we can't signal it


class PidLock:
    def __init__(self, lock_path: Path) -> None:
        self._path = lock_path

    def acquire(self) -> bool:
        """Return True if lock acquired, False if another process holds it."""
        if self._path.exists():
            try:
                pid = int(self._path.read_text().strip())
                if _process_alive(pid):
                    log.warning("collectors already running as PID %d", pid)
                    return False
                log.info("Stale PID lock (PID %d dead) — removing.", pid)
                self._path.unlink(missing_ok=True)
            except (ValueError, OSError):
                self._path.unlink(missing_ok=True)

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(str(os.getpid()))
        return True

    def release(self) -> None:
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            pass
