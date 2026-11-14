# Yomu Note v0.7.6.a — version-label / save-metadata patch

This patch applies on top of the **v0.7.6a Integrated Offline OCR** source archive.
It changes only version display, application metadata, installer release label,
and the informational application-version tags written into save manifests.

## Apply the small patch to your existing extracted source

Place `YomuNote-0.7.6.a-version.patch` in the folder containing `main.py`.
Then, from that folder, run:

**Windows PowerShell**

```powershell
git apply --check .\YomuNote-0.7.6.a-version.patch
git apply .\YomuNote-0.7.6.a-version.patch
```

**macOS Terminal**

```bash
git apply --check ./YomuNote-0.7.6.a-version.patch
git apply ./YomuNote-0.7.6.a-version.patch
```

Alternatively, use the complete updated source ZIP directly (no patch needed).
Do **not** apply this twice or to an older source version.

**Important:** The patch does not edit an already built `.exe` or `.app`.
Rebuild using the usual scripts to see the updated About window in those apps.

## Save file metadata

- SQLite `.yomunote` -> `meta` table -> `manifest` JSON: `app_version: "0.7.6.a"`.
- Each saved tab's embedded `project.json`: `app_version: "0.7.6.a"`.
- Older notebook/project manifests with no `app_version` remain compatible.
- `version: 5` for the notebook and `version: 4` for tab projects are
  **file format numbers**, not app release numbers, and must not be replaced.
- A notebook saved with the new app receives the current app tag even when
  its contents have not changed; older per-tab project files get the new tag
  when that tab project itself is next saved.

To validate without Qt, run `python -m pytest -q tests/test_version_metadata_v076a.py`.
