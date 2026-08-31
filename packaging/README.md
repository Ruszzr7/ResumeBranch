# Windows single-user installation package

This directory builds the third delivery path: a Windows installer for the frozen single-user profile. It does not replace or modify the source development/testing scripts or the multi-user Docker deployment.

## Build prerequisites

Build on Windows x64 with:

- Python 3.11 and a prepared `.venv-win` containing the locked backend dependencies.
- Node.js/npm with `frontend/node_modules` installed from `frontend/package-lock.json`.
- The .NET SDK, because the build publishes the self-contained GUI launcher.
- Network access on the first build, or previously cached verified assets under `%LOCALAPPDATA%\ResumeBranchPackager`.
- A clean tracked Git worktree. The build stops if tracked files already contain changes; existing untracked packaging outputs are allowed.

The build script downloads and verifies the private Python runtime, Nginx, Headless Chromium, Poppler, Inno Setup, and the Inno Setup language file. Inno Setup is a build-time compiler only; end users do not need to install it.

Build on Windows x64 from the repository root:

```powershell
.\packaging\build-installer.ps1
```

Use `-SkipTests` only when the maintainer has separately completed the required backend and frontend checks:

```powershell
.\packaging\build-installer.ps1 -SkipTests
```

The build runs the existing backend and frontend tests, creates the Vue production bundle, assembles a private Python runtime, Chromium, Poppler, and Nginx, then produces:

```text
output/installer/ResumeBranch-Setup-v1.1.2-x64.exe
```

Downloaded build inputs are pinned by SHA-256 and cached under `%LOCALAPPDATA%\ResumeBranchPackager`. They are build-time inputs only; the final installer does not download or register system-wide dependencies. The installed launcher starts the existing single-user SQLite profile on `127.0.0.1`, serves the prebuilt frontend on port `5173`, and opens the default browser.

The installer has no updater and creates no Start menu entry. The optional desktop shortcut points directly to `ResumeBranch.exe`.
