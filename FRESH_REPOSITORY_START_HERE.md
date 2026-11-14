# Fresh Yomu Note repository source — v0.8.1b-rc4 candidate

Source origin: https://github.com/alteredwavestudios/Yomu-Note.git
Source branch: fix/rc4-windows-installer-linux-source
Source base commit: 4038e32e35d947fc52556a556c315922c130e7e1

Includes tracked source, build scripts, GitHub Actions workflows, tests,
documentation, assets, and a correction to the Linux source-only release
contract tests/docs. No local user notebooks, Python environments, build
caches, generated installers or .git history were copied.

Create a NEW, EMPTY GitHub repository. Extract this ZIP, open a terminal in
its Yomu-Note folder, then run:

    git init -b main
    git add .
    git commit -m "Initial Yomu Note v0.8.1b preview source"
    git remote add origin https://github.com/YOUR-OWNER/YOUR-NEW-REPO.git
    git push -u origin main

Review tracked assets, licences and notices before publishing. Replace the
old repository URLs in documentation if you chose not to supply the
--new-repository-url option. Do not add real .yomunote notebooks or secrets.

After source CI is green, use a NEW, unused candidate release tag (for example
v0.8.1b-rc4 only if it does not already exist in the new repository). This
starts the release workflow for Windows + macOS arm64 + macOS Intel and makes
an unpublished draft. Test the downloaded installers before publishing.

IMPORTANT: Build scripts install or download developer build-time dependencies
(Python packages, Inno Setup, Tesseract, etc.) and do not ship their own binary
installers inside this source ZIP. This archive has not been compiled or
verified on fresh Windows/macOS machines. Linux users run from source.
