# Yomu Note v0.8.1b — GitHub publishing status

Updated on 11 November 2026 for the v0.8.1b release candidate.

## Verified in this preparation environment

- v0.8.1b builds on the v0.8.1a hardening source and subsequent regression fixes.
- Screenshots added to `docs/screenshots/` (four primary feature screenshots plus the Preferences screenshot).
- README, quick start, feature guide, install guide, contribution/security policies, issue templates, release notes, CI and release workflow files added.
- Old historical release documents organised under `docs/history/` and `docs/testing/`.
- Linux source build updated to stage Tesseract and check for missing OCR-native libraries; macOS build no longer pauses for input during CI.
- `python -m compileall -q main.py yomunote ocr_packaging tests` completed.
- Automated suite: **434 passed, 48 Qt-dependent tests skipped, 3 subtests passed**.
- Git ignore rules checked against build caches, virtual environments and personal `.yomunote` files.

## Not yet completed — do not describe these as done

- Release-candidate changes have not yet been committed and pushed to `main`.
- No public GitHub Release was published.
- No Windows, macOS or Linux native installer binary was built in this environment.
- The v0.8.1b GitHub release workflow still needs to complete successfully on hosted Windows, macOS and Linux runners.
- Clean-machine bundled-OCR, Tab Exchange and GUI smoke tests are still needed on each platform.
- macOS DMGs are unsigned and not notarised; Windows installer is unsigned; Linux AppImage portability needs distro tests.
- Candidate GPL-3.0-or-later licence files are prepared; third-party binary redistribution notices and creator permissions still need release-specific verification.

## Release order

1. Confirm GPL-3.0-or-later copyright-holder approval, audit all public content and third-party redistribution notices, and optionally enable GitHub's private vulnerability reporting.
2. Publish the GitHub repository after reviewing the initial commit.
3. After the `main` source checks pass, push a NEW tag `v0.8.1b` (do not move `v0.8.1a`) to trigger GitHub Actions release builds.
4. Confirm all four release artifacts and checksum file exist in the **unpublished draft**.
5. Test installed builds on clean Windows/macOS/Linux environments and check privacy/licensing.
6. Publish the draft as a **pre-release** and point users to Releases, not source-code ZIPs.
