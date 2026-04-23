# Grid Orchestrator

Grid Orchestrator is a trading operations project for managing GinArea-style grid bots and their supporting market analysis workflow. The workspace contains the Telegram runtime, backtest tooling, frozen datasets, and orchestration state used to evaluate and operate the strategy stack.

TZ-011 fixes canonical backtest isolation and prepares the workspace for a future git migration by separating immutable baseline state from live mutable state.

## Quick Start

1. Create and activate a local virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Configure your local secrets outside the repo through `.env` or `bot_local_config.json`.
4. Start the unified runtime with `RUN_APP.bat`.

## Tests

- Run the regression suite with `RUN_TESTS.bat`.
- After TZ-011, the suite is expected to pass with the new baseline tests included.

## Baseline

- Canonical baseline documentation lives in `BASELINE.md`.
- Immutable baseline state files live in `state/baseline/*.json`.
- Live mutable files in `state/*.json` are intentionally ignored by `.gitignore`.
- Pattern memory CSV files in `state/` remain committed reference data.

## Architecture

- Runtime and orchestration docs live under `docs/`.
- Baseline and determinism behavior are documented in `BASELINE.md`.
- TZ-specific acceptance and design notes remain in the root `TZ-*.md` files and companion docs.
