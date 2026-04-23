ZERO CLICK MODE - CHAT BOT VERSION 2

Files:
- INIT_GITHUB_PRIVATE_REPO.bat
- PUSH_UPDATE.bat
- MAKE_RELEASE_TAG.bat
- OPEN_GITHUB_ACTIONS.bat
- _GITHUB_RUNTIME.bat

How it works:
1. INIT_GITHUB_PRIVATE_REPO.bat
   - finds Git automatically
   - supports Git for Windows and GitHub Desktop bundled Git
   - sets repo identity for this repository
   - links private origin
   - runs first push
   - if GitHub CLI exists, it can open browser login once

2. PUSH_UPDATE.bat
   - can auto-run init if repo is missing
   - reads commit message from VERSION.txt
   - adds, commits, pushes in one run

3. MAKE_RELEASE_TAG.bat
   - reads tag from VERSION.txt
   - creates commit if needed
   - pushes branch and tag
   - GitHub workflow can create release ZIP automatically

4. OPEN_GITHUB_ACTIONS.bat
   - opens Actions page for the repository

Notes:
- GitHub Desktop can be installed instead of adding Git manually to PATH.
- GitKraken alone is not guaranteed to expose git.exe for batch automation.
- GitHub Actions workflow files stay in .github/workflows.
