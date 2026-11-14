# v0.7.6 stability audit — worker lifetime and autosave

**Base:** v0.7.5. **Scope:** autosave scheduling and the lifetime of closed or
replaced notebook workspaces. No new features, notebook database format changes,
or changes to page imports, text rendering, OCR or animations.

## What changed and why

### Autosave (bounded dirty-only frequency)

The prior 2-second idle + 20-second maximum timers could write often during
small edits. A single 60,000 ms one-shot timer now begins on the first unsaved
change; subsequent keystrokes do not reset it. After the save succeeds,
`_dirty=False` disarms it. Save failures retain `_dirty=True`, emit the
existing status message, and retry after one minute. Clean tabs never start
an autosave timer. Immediate saves on tab switch, explicit Save, close, and
before backup are retained as protection against unexpected exits.

**Trade-off:** a hard crash could lose up to roughly one minute of changes
since the most recent successful save (or a little more after disk errors or
while a blocking operation prevents Qt's event loop from running). This is
not a guaranteed upper limit and is not a substitute for normal backups.

### Retired notebooks (previously high risk)

Previously, `MainWindow._retired_notebooks` retained every old notebook until
app exit, including large unpacked source assets. The new
`RetiredNotebookQueue` instead waits until all owning panes report no active
background tasks. In a two-step GUI timer, it calls QWidget.deleteLater()
for the old panes and then closes the old notebook's TemporaryDirectory.
Workers use `GuiReceiver.finished`, queued to the main thread, to remove tasks
from each pane's `_tasks` set, so an active background PDF/OCR read prevents
premature workspace deletion. Cleanup retries Windows transient OSErrors.

Detached panes are marked closed before retiring. This suppresses their
late worker UI handlers, while the receiver still removes completed tasks.
`_last_active_pane` is cleared on notebook close. All still-dirty VISIBLE
panes are saved before whole-notebook retirement. Deleted/parked tab history
is explicitly preserved within the active notebook.

## What has NOT been claimed fixed

1. **Deleted tabs inside an OPEN notebook** are still kept for Undo; this
   resource retention is intentional and currently bounded mainly by the
   normal history limit, not a measured native QTextDocument memory cap.
2. **Workers that never finish** must retain source files. There is no hard
   cancellation time limit in this change. Native profiling and cancellation
   controls can follow once worker ownership is thoroughly tested.
3. **Large saves and 10-minute recovery backups still run synchronously** on
   the main UI thread. This build reduces save frequency but does not remove
   potential pauses on slow disks or large projects.
4. **Cross-tab transfers** are not yet fully atomic across two tab manifests;
   that's still an independent corruption-risk item for a later hardening pass.
5. **Native GUI validation is unavailable here.** The Qt tests are included
   for execution on supported Windows/macOS machines with PySide6 installed.
6. **App exit while tasks run** still depends on Qt/Python shutdown semantics;
   it has not been redesigned for non-blocking cancellation in this build.

## Regression and integrity checks

- Pure-Python queue tests cover unfinished workers, delayed cleanup, duplicate
  pane references, concurrent retired notebooks, empty notebooks, and Windows
  transient lock retry.
- Optional GUI tests validate the 60s timer, no repeated keystroke debouncing,
  clean-tab behaviour, and notebook switching with a simulated outstanding job.
- Existing notebook storage, rich-text, Undo, annotations, import, and legacy
  extension regressions are unchanged.
- Use `TEST_WINDOWS_MAC_V076.md` to exercise the actual native lifetime paths.

**Release posture:** v0.7.6 is a candidate, not proof of memory-leak-free,
corruption-proof, or penetration-tested operation. Keep a backup of your
working v0.7.5 and important notebooks until tests pass on your machines.
