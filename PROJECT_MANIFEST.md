# PROJECT MANIFEST

## Current version
V17.10.42-smoke-test-gate

## Root bat files kept in release
- RUN_BOT.bat
- RUN_TESTS.bat
- SMOKE_TEST.bat
- INSTALL_GIT_HOOKS.bat
- MAKE_RELEASE.bat
- PUSH_RELEASE.bat

## Root bat/cmd files moved out of the way
Stored in `tools/legacy_bat/` to keep the release root clean and reduce operational confusion.

## Stability status
- Regression Shield present
- release gate active
- git hooks active
- cleanup base complete
- bat layout minimized

## Release safety additions
- SMOKE_TEST.bat
- tools/smoke_test.py
- release blocked if live run is empty or contains Traceback/Exception
