# Build / publish installers (maintainer guide)

This repository has two GitHub Actions workflows:

- **Check source:** runs syntax checks and the Python test suite on Windows, Linux and Apple Silicon macOS.
- **Build draft release:** when a `v*` tag is pushed, builds a Windows setup EXE and two macOS DMGs. Linux stays source-only and is tested through **Check source**, not release packaging. It **never publishes** the release automatically. All three installer assets must be present before the draft is created.

## One-time requirements

- The GitHub repository exists, and you have permission to push commits and tags.
- You have chosen a source-code licence (see [LICENSING_DECISION.md](../LICENSING_DECISION.md)) and reviewed third-party redistribution notices.
- **GitHub Actions** is enabled, with `GITHUB_TOKEN` allowed to create GitHub Releases as specified by the publish job (`contents: write`). If Actions defaults block it, adjust repository Settings → Actions → General → Workflow permissions.
- You have tested local `.yomunote` round-trips with **copies** of coursework, including Tab Exchange and OCR.

## Publishing your first commit — GitHub Desktop (Windows)

1. Extract the **GitHub-ready ZIP** to a permanent folder (for example `Documents\Yomu-Note`).
2. Open [GitHub Desktop](https://desktop.github.com/), choose **File → Add local repository…**, point at that folder and choose **Create a repository** if prompted. Do **not** add your personal notebooks to the folder.
3. Review the file list and `.gitignore`. Confirm only source, assets, screenshots, documentation and workflow files are included.
4. Enter the commit summary **`Initial public preview: Yomu Note v0.8.1b`**, choose **Commit to main**, and then **Publish repository**. Choose public only when you're ready for all files to be visible.
5. Open the repository's GitHub page and check that the screenshots and README render properly.

You can also use Git from PowerShell:

```powershell
git init -b main
git add .
git status
git commit -m "Initial public preview: Yomu Note v0.8.1b"
# Create an empty GitHub repository, then use the URL GitHub provides:
git remote add origin https://github.com/YOUR-ACCOUNT/Yomu-Note.git
git push -u origin main
```

Do **not** include a real notebook `.yomunote`, API tokens, passwords, signing keys or local virtual environments in the commit.

## Creating a draft installer release

Once the `main` branch is on GitHub and the native build dependencies are ready, create and push the exact tag:

```powershell
git tag v0.8.2-rc1
git push origin v0.8.2-rc1
```

That triggers `.github/workflows/release.yml`. Check **Actions** for the Windows, Mac ARM and Mac Intel packaging jobs. Linux source tests continue separately under **Check source**. The workflow builds the three native installer variants on GitHub-hosted machines and runs tests/packaged-OCR verification. **A green workflow is not equivalent to a clean-machine GUI test.**

When all jobs succeed, GitHub automatically creates an **unpublished draft Release** with the three native installer binaries and SHA256 checksums. Open **Releases → Drafts**, download each asset, test it on a clean machine, and then choose **Publish release**. Keep **Pre-release** checked for v0.8.2-rc1.

If a job fails, **do not publish the release**. Inspect that job's logs, fix the build, and produce a fresh candidate tag or rerun the same tag after a safe CI-only fix. Avoid silently moving an already published tag.

## Native builders and toolchains

| Platform | Release format | Build-only dependencies |
| --- | --- | --- |
| Windows x64 | Inno Setup `.exe` | Python, PyInstaller, Tesseract, Inno Setup |
| macOS arm64 | Unsigned `.dmg` containing `.app` | Python, PyInstaller, Homebrew Tesseract, hdiutil |
| macOS Intel | Unsigned `.dmg` containing `.app` | As above, on Intel runner |

Windows and macOS scripts package OCR executable and language data, verify live recognition and check native libraries to the degree supported by the build platform. Linux users run `run-linux.sh` (source) or `build-linux.sh` (optional local standalone directory) with their distro's Tesseract. Some Office/EPUB imports require additional converters.

**Security/accuracy note:** Native builds remain **not fully reproducible** because dependency ranges and some build tooling are not pinned to immutable versions. Pin a tested dependency set and audit the full supply chain for v1.0. Signing, notarisation and installer security review remain future release gates.

## Local platform commands (for debugging CI)

Windows PowerShell (after a `.venv` has been created using the launcher or Python):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build-windows.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build-installer-windows.ps1
```

macOS: `CI=1 zsh build-mac.command` then `bash scripts/package-macos-dmg.sh`.

Linux: after installing the distro prerequisites, run `sh run-linux.sh` to launch from source, or `bash build-linux.sh` for a locally built standalone app directory (no AppImage).

## Release acceptance checklist

- [ ] All CI and platform build jobs green
- [ ] Windows installer launches, saves and reopens a notebook, supports OCR and Tab Exchange
- [ ] macOS ARM and Intel builds launch on clean machines with **no Homebrew installed**, with OCR working
- [ ] Linux source checkout launches on a representative supported distribution with system OCR working (no AppImage is shipped)
- [ ] Smart Import chapter checkboxes tolerate many rapid toggles without crashing
- [ ] Cross-platform export/import preserves original PDFs, group structure, notes, annotations and reading progress
- [ ] Import Undo/Redo (including edit-then-redo) works; saved notebooks reopen correctly
- [ ] `LICENSE` and `THIRD_PARTY_NOTICES.md` bundled; complete **native dependency** notices and Qt/PDFium/OCR obligations reviewed per platform
- [ ] User-facing screenshots and licence/redistribution notices reviewed
- [ ] No notebook data, signing keys, passwords, or temporary build artefacts in GitHub tree
- [ ] Assets and checksums verified, then draft Release published deliberately
