"""Tests for tools/install_hooks.py + .githooks/pre-commit syntax."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import install_hooks


# ---------------------------------------------------------------------------
# .githooks/pre-commit syntax
# ---------------------------------------------------------------------------

class TestPreCommitSyntax:
    """Bash syntax of the pre-commit hook must parse cleanly."""

    def test_pre_commit_syntax_valid(self):
        """`bash -n` parses .githooks/pre-commit without error."""
        hook = ROOT / ".githooks" / "pre-commit"
        assert hook.exists(), f"{hook} missing"
        bash = shutil.which("bash")
        if bash is None:
            pytest.skip("bash not on PATH (needed for syntax check)")
        result = subprocess.run(
            [bash, "-n", str(hook)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, (
            f"bash -n failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        )

    def test_pre_commit_invokes_validate_tz(self):
        """Hook must reference tools/validate_tz.py."""
        hook = ROOT / ".githooks" / "pre-commit"
        text = hook.read_text(encoding="utf-8")
        assert "tools/validate_tz.py" in text

    def test_pre_commit_filters_docs_tz_pattern(self):
        """Hook must scope validation to docs/tz/*.md staged files (case-insensitive).

        Windows filesystems are case-insensitive, so the regex uses `grep -i`
        and a lowercase pattern. Both `docs/TZ/...` and `docs/tz/...` must
        match the staged-files filter.
        """
        hook = ROOT / ".githooks" / "pre-commit"
        text = hook.read_text(encoding="utf-8")
        # Case-insensitive grep flag must be present
        assert "grep -iE" in text
        # The (lowercase) path pattern must be the docs/tz/ scope
        assert "docs/tz/" in text


# ---------------------------------------------------------------------------
# install_hooks helpers
# ---------------------------------------------------------------------------

class TestInstallHooksGitConfig:
    """install() runs `git config core.hooksPath .githooks` and verifies."""

    def test_install_sets_hooks_path(self):
        calls: list[tuple[str, ...]] = []

        def fake_git(*args, cwd=None):
            calls.append(args)
            if args[:2] == ("config", "core.hooksPath"):
                # set
                return 0, "", ""
            if args[:3] == ("config", "--get", "core.hooksPath"):
                # first call returns previous, later returns new
                # → simulate fresh install: previous unset, after install returns ".githooks"
                if calls.count(args) == 1:
                    return 1, "", ""  # unset
                return 0, ".githooks", ""
            return 0, "", ""

        with patch("tools.install_hooks._git", side_effect=fake_git):
            summary = install_hooks.install()

        # Confirm we attempted to set core.hooksPath to .githooks
        assert any(
            args[:2] == ("config", "core.hooksPath") and ".githooks" in args
            for args in calls
        ), f"set call never happened. calls={calls}"
        assert summary["new_hooks_path"] == ".githooks"
        assert summary["ok"] is True

    def test_install_idempotent_when_already_configured(self):
        """Re-running install when already configured must succeed and flag it."""
        def fake_git(*args, cwd=None):
            if args[:3] == ("config", "--get", "core.hooksPath"):
                return 0, ".githooks", ""
            if args[:2] == ("config", "core.hooksPath"):
                return 0, "", ""
            return 0, "", ""

        with patch("tools.install_hooks._git", side_effect=fake_git):
            summary = install_hooks.install()

        assert summary["already_configured"] is True
        assert summary["ok"] is True

    def test_install_fails_when_hooks_dir_missing(self, tmp_path):
        """install() raises if .githooks/ folder is missing."""
        with patch("tools.install_hooks.HOOKS_DIR", tmp_path / "nonexistent"):
            with pytest.raises(FileNotFoundError):
                install_hooks.install()

    def test_check_returns_status(self):
        """check() reports status without modifying git config."""
        with patch(
            "tools.install_hooks._git",
            return_value=(0, ".githooks", ""),
        ):
            result = install_hooks.check()
        assert result["current_hooks_path"] == ".githooks"
        assert result["expected_hooks_path"] == ".githooks"
        assert result["ok"] is True

    def test_check_detects_unset_hooks_path(self):
        """check() returns ok=False when core.hooksPath is not configured."""
        with patch("tools.install_hooks._git", return_value=(1, "", "")):
            result = install_hooks.check()
        assert result["current_hooks_path"] == ""
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

class TestInstallHooksCLI:
    def test_check_subcommand_exits_0_when_ok(self, capsys):
        with patch(
            "tools.install_hooks._git",
            return_value=(0, ".githooks", ""),
        ):
            rc = install_hooks.main(["--check"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "OK" in captured.out

    def test_check_subcommand_exits_1_when_unset(self, capsys):
        with patch("tools.install_hooks._git", return_value=(1, "", "")):
            rc = install_hooks.main(["--check"])
        assert rc == 1
