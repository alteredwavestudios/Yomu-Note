# Yomu Note v0.7.5 — Limited stability hardening

This candidate is derived from v0.7.4, with no change to the saved notebook schema or features. The only functional changes are: (1) reject Windows-illegal asset filenames consistently on all OSes; (2) fail/rollback incomplete or unexpectedly growing asset reads during SQLite streaming saves; (3) cap cache-folder write tracking at 512 entries with a worker-thread lock; and (4) scrub embedded v2/v3 migration manifest backups from newly created **clean share copies only**, VACUUMing the output afterward. Existing notebooks and historical recovery backups are never altered by the clean-share change.

See `AUDIT_075.md` for outstanding architecture risks, and `TEST_WINDOWS_V075.md` before replacing a working Windows install. This candidate has not been tested with PySide6 on Windows.
