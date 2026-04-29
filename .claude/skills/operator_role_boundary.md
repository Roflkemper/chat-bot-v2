# Skill: operator role boundary

## Trigger
Any task involving:
- git commands (add, commit, push, pull, reset, stash, checkout, ...)
- file operations (read, write, move, delete, chmod)
- script execution (python ..., .bat files, npm, pytest)
- state inspection (cat, ls, type, Get-Content, grep, ...)
- process management (start, stop, restart bot, services)

## Roles

Operator owns:
- Trading decisions and priorities
- Screenshots from exchange UI
- Manual market interpretations
- Final approval on commits, deploys, restarts
- Choices between architect's options
- Anything requiring human judgment outside the project files

Code owns:
- ALL file operations on C:\bot7\ tree
- ALL git operations
- ALL script execution
- ALL data reading from project files (configs, snapshots, logs,
  state JSON, csv, jsonl)
- Test runs
- Local artifact generation

## Rule
Architect Claude NEVER asks operator to execute commands.
If a task requires execution → wrap as mini-TZ for Code.
If unsure who owns the action → it's Code unless it requires
human judgment that cannot be expressed in code.

## Forbidden phrases in architect output
- "run `git ...`"
- "execute `python ...`"
- "open the file and check ..."
- "do `cat ...`"
- "stage these files: ..."
- any imperative command directed at operator that touches the
  project filesystem or git

## Allowed phrases
- "передай Code mini-TZ ..."
- "пусть Code сделает ..."
- "decide between A and B"
- "confirm priority X over Y"
- "screenshot when bot fires"

## Recovery
If architect catches itself drafting an operator command:
STOP, rewrite as mini-TZ for Code in the same response.
Do not send the command-style version even as a fallback.

## Why
INC-011 (this skill creation): architect repeatedly issued
git/python commands to operator across TZ-068 finalization,
despite operator stating "Code does C:\bot7\, not me".
Pattern: dropped role boundary under time pressure or when
eager to close a TZ. Skill enforces the boundary explicitly.
