# Windows GUI checklist — Yomu Note v0.7.2b

Run the included source (`run-windows.bat`) using an environment with the
`requirements.txt` dependencies installed. Back up any important `.yominote`
notebooks before trying a candidate version.

1. **Checkbox hits:** In the Groups view, click directly on and 3–6 pixels
   *beside* a checkbox on a normal page and on a nested subgroup. Both should
   toggle once, immediately update progress, and show the checkmark/dash.
   Clicking farther away should select or navigate, not toggle. Use Ctrl+Z
   and Ctrl+Y to confirm exactly one Undo/Redo step per toggle.
2. **Layout widths:** Drag the left splitter through approx. 420, 275, 218,
   135 and 80 px. Large widths show names; medium widths show clean picture
   rows and folder names; narrow widths show an intentional tiny rail with
   no horizontal scrollbar. The group/ungroup operations, collapsed arrows,
   tooltips, selection, drag/drop and rename still work at normal width.
3. **Wide thumbnails:** At 400–520 px, Groups view thumbnails become a bit
   larger; the separate Thumbnails view fills the extra room, with no stretch
   distortion. Scroll through 100+ pages and ensure off-screen thumbnails
   continue evicting normally, and no extra memory spikes are observed.
4. **Actions at tiny width:** Add, Smart Import, Blank, Rename, Remove and
   Undo must remain accessible in the (...) overflow menu even when +Add
   itself is hidden. Switch Groups/Pages, and cycle width presets.
5. **Progress:** Tick/un-tick a page and then a group. The progress bar rises
   and falls smoothly, only rising flashes, and completion celebrations do
   not replay when reopening the project or Undo/Redo.
6. **Notices:** Trigger a Pomodoro finished-session reminder and a reading
   completion. Notifications should appear with valid themed backgrounds,
   Japanese kaomoji and **no** repeated 'Could not parse stylesheet' console
   messages.
7. **Preferences:** On a fresh Windows profile, Playful and Crisp should be
   selected. On an existing profile where Gentle/None or Off/Gentle were
   explicitly saved, those preferences must remain. Toggle Reduce animations.
8. **Themes:** Test Strawberry Milkshake, Melon Soda Pop, Peach Mochi,
   Candy Cloud, Grape Fizz Night, Arcade Hearts, Sakura Washi and Midnight
   Indigo. Text, checkboxes, modals and progress must remain readable.
9. **Persistence:** Save/reopen a complex notebook with nested groups; verify
   page positions, reading states and annotations are unchanged. Confirm
   adding and closing tabs do not raise deleted-widget errors.

Optional GUI regression run: `python -m pytest tests/test_v072b_navigator_gui.py -q`

Source-only automated test results are not a substitute for the above native
Windows/Qt checks. No Windows binary is built in the Linux test environment.
