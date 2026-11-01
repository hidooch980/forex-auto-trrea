# Publish this project to GitHub safely

Target repository: https://github.com/hidooch980/forex-auto-trrea

## Important: credentials are not included

This archive intentionally contains **no GitHub password, access token, SSH private key, or ChatGPT credential**. Those secrets must never be embedded in a ZIP or committed to a repository. Authenticate on your own computer using Git Credential Manager, GitHub CLI (`gh auth login`), or an SSH key configured with GitHub.

## Windows PowerShell

1. Extract this ZIP.
2. Open PowerShell in the extracted `forex_ai_hybrid_scalper_github` folder.
3. Run:

```powershell
git --version
git clone https://github.com/hidooch980/forex-auto-trrea.git ..\forex-auto-trrea
Copy-Item .\* ..\forex-auto-trrea\ -Recurse -Force
Set-Location ..\forex-auto-trrea
git status
git add .
git commit -m "Add Forex AI Hybrid Scalper project"
git push
```

If the repository is empty, these commands should publish the project after GitHub authentication. If `git clone` says the repository does not exist or access is denied, verify the repository URL and your GitHub permissions first. If `git push` reports that the remote contains work you do not have, stop and inspect `git status` / `git log`; do not force-push.

## Ubuntu / Linux / macOS

```bash
git --version
git clone https://github.com/hidooch980/forex-auto-trrea.git ../forex-auto-trrea
cp -a . ../forex-auto-trrea/
cd ../forex-auto-trrea
git status
git add .
git commit -m "Add Forex AI Hybrid Scalper project"
git push
```

Do not paste tokens or passwords into chat, source files, shell history, or Git remote URLs. Use an interactive credential helper or SSH authentication.
