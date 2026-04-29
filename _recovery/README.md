# TZ-049 Recovery Log — 2026-04-29

## What Happened

The `collectors/` package (live market data collector writing 1.4MB/s to parquet)
existed only as an untracked directory in `C:\bot7`. It was never committed to git.
When the directory was deleted (likely via `CLEANUP_CORE.bat` or manual cleanup),
the source files were lost from disk.

The running process (PID=5136) still held the modules in memory (Python loads modules
at startup and doesn't need the files after that), but the on-disk sources were gone.

## How Sources Were Found

`git fsck --full --no-reflogs --unreachable --lost-found` revealed **640 dangling trees**
in `.git/objects/`. Six of them contained a complete `collectors/` package (15 files each):

| Tree hash | storage.py size | Source |
|---|---|---|
| `c8801caa` ✅ **SELECTED** | 8306 bytes | Stash untracked-files commit `1cc6e4a7` @ 1777413803 (~2026-04-26) |
| `fe053ae4` | 7696 bytes | Bare tree, no commit |
| `1d4be8f7` | 7696 bytes | Bare tree, no commit |
| `9752f8ac` | 7696 bytes | Bare tree, no commit |
| `91e4476b` | 7696 bytes | Bare tree, no commit |
| `09145028` | 7575 bytes | Bare tree, no commit |

**Selection criteria:** `c8801caa` chosen because:
1. Only tree with an associated dangling commit (with timestamp)
2. Largest storage.py (8306 bytes) — most feature-complete version
3. Its main.py blob (`3998c29c`) matches 4 out of 5 other trees

## Recovery Method

Used `GIT_INDEX_FILE` temp index to extract without touching the main index:

```powershell
$env:GIT_INDEX_FILE = "$env:TEMP\recovery_collectors.index"
cd C:\bot7
git read-tree c8801caa2a00c8877e50f8bc9b7ce4aa34c6b4fe
git checkout-index -a --prefix=_recovery/restored/
Remove-Item Env:\GIT_INDEX_FILE
```

Then copied from `_recovery/restored/collectors/` → `C:\bot7\collectors/`.
Companion files (scripts/watchdog.py, scripts/run_collectors.bat,
scripts/smoke_collectors.py, tests/test_collectors_parsers.py) copied similarly.

## Verification

```
python -c "import collectors; import collectors.main; import collectors.storage"
# → OK

pytest tests/test_collectors_parsers.py
# → 36 passed

pytest tests/
# → 310 passed, 12 failed (12 failures are pre-existing, unrelated to TZ-049)
```

## Original .pyc Inventory

The original `.pyc` files were in `C:\bot7\collectors\__pycache__\` which was deleted
along with the source directory. Recovery was possible only because git stash had
previously captured the untracked files.

## Disassembly

Disassembly of recovered files not performed (source recovery via git blobs is
bit-exact — no decompilation needed).

## Lessons / Invariant

Any executable Python code in this project MUST be in git with source files.
Bytecode-only deployment is prohibited.
See TZ-DEBT-04 in docs/MASTER.md §Долги.
