# v0.7.2a Windows acceptance checks

Extract into a **new folder**; don't overwrite your working version. Keep a backup
of your existing `.yominote` notebooks. This release has no storage migration.

Run `run-windows.bat` or your usual Windows build path. For automated Qt checks,
open PowerShell in the extracted project (with PySide6/test requirements installed):

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_v071a_progress_lifecycle_gui.py tests/test_v071_progress_gui.py tests/test_v072a_rewards_gui.py
```

Manual visual and interaction checks:

1. Light themes: Washi, Matcha, Yuzu, Lilac and Modern Light. In Groups view,
   mark one page read: the checkmark must be plainly visible *inside* its box.
   Mark part of a subgroup: parent must show a clearly visible dash.
2. Switch to Midnight Indigo, Shibui Graphite and other dark palettes and
   verify the same group/page tick and partial states and accent contrast.
3. Tick/untick several pages: active-tab, nested-group and notebook-header bars
   must ease up/down. Only increases glint; no glint on decreases.
4. Create a two-page group and another tab. Complete the group; expect named
   Kawaii toast + small confetti. Complete a tab; larger confetti. Complete the
   whole notebook; grand celebration *once*, without overlapping lower tiers.
5. Test 25%, 50%, 75% notebook threshold crossings; these are quiet toasts.
   Unchecking/rechecking should not display an unwanted duplicate immediately.
6. Test Undo/Redo and reopening a completed notebook: restored read flags and
   bars must work, but no celebrations should replay.
7. In Preferences, switch celebration checkboxes and motion modes. Try Reduce
   animations: progress should jump to final values, no flash or confetti.
8. Set Pomodoro to 1 minute and complete a focus session and break. A themed,
   non-modal card should show each new message; it must not steal focus or
   interrupt reading. Keep it overdue to see progressively sillier messages
   (but no messages at 10+ minutes). Check both sound on and sound off.
9. Try adding, renaming, switching and deleting tabs, and marking pages while
   creating new tabs. No deleted QLabel/shiboken exceptions should appear.
10. Test very long group names, titles containing `<` and `&`, and resizing
    the window while a notice is visible. Notice text should never be parsed
    as markup, and the workspace should remain clickable.

Do not ship as a stable Windows release until those visual tests pass.
