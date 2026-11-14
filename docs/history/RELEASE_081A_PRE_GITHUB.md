# v0.8.1a — pre-GitHub hardening candidate

**Based on the user-confirmed working v0.8.1 Tab Exchange.** No new feature is intentionally included.

- Preflight untrusted shared notebook manifests and per-tab metadata before reading large JSON strings into memory.
- Check actual SQLite BLOB lengths, not just untrusted declared sizes; validate all selected assets *before* copying a multi-tab batch.
- Preflight total notebook extraction size/file count; reject invalid file timestamps early.
- Check SQLite quick_check result on new shared notebooks.
- Block redundant checkbox-change signals during Select All / None in Tab Exchange.
- Raise minimum dependency versions to incorporate late-2026 upstream security fixes. **These new minimums were not installable in the audit environment**; native Windows/macOS builds need smoke tests before release.
- Version becomes **v0.8.1a**; notebook file format remains **5**.
- Add beginner-friendly in-code explanations and a new architecture walkthrough.
- Rewrite the front-page README for GitHub; preserve the former README under `docs/`.
- Add explicit security audit, GitHub licensing/commit checklist and adversarial storage tests.

**Automated results:** 430 passed; 48 GUI-dependent tests skipped; 3 passed subtests. Source compiles. Read `SECURITY_AUDIT_081A.md` for limitations.
