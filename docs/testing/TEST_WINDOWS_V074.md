# Windows acceptance tests — Yomu Note v0.7.4

**Use a backup/copy** of every important notebook. Run this version from a
separate extracted source folder, not over your known-working installation.

## A. Data integrity / legacy extension
1. Copy a valuable `.yominote` notebook (with at least two tabs). Open it.
2. Confirm a new `.yomunote` file appears **alongside** the unchanged original.
3. Confirm both tabs' group names, reading states, page titles, notes text,
   formatting, fonts, hyperlinks, annotations and progress totals survived.
4. Save, close and reopen the `.yomunote` copy. Verify again.
5. Reopen the old `.yominote` original. Confirm it remains independently
   readable, and no newer `.yomunote` file was overwritten.
6. Create a new notebook and confirm `.yomunote` extension by default.

## B. Group labels and thumbnails
1. Open a populated tab whose Groups are collapsed; switch tabs repeatedly.
   Verify labels load immediately, even before all thumbnails appear.
2. Resize the navigator from 540px down to the smallest rail and back.
   Verify group labels are elided rather than vanishing due to stale mode.
3. Scroll across 100+ pages, forcing thumbnail cache eviction; labels and
   group counts must remain stable and not depend on thumbnail availability.
4. Check a group with hundreds of pages, including 100%, 0%, and partial
   progress; counter must not overlap the meter.
5. Right-click a **page** in Groups and choose Remove this page. Check the
   confirmation and the removal target; Undo restores original order/group.
6. Check the navigator's other mode says Individual and behaves unchanged.
7. Hover tab titles and verify the close cross has padding on the right.

## C. Multiple notes pages within one tab
1. Open a legacy tab with formatted HTML notes, a table and a page hyperlink.
   Check these are in Notes 1 without any conversion or stripped styling.
2. Create Notes 2 and Notes 3; type different formatting, fonts, links,
   lists, paragraph spacing, tables and page links in each.
3. Cycle through pages repeatedly (arrows and dropdown). Verify their texts
   are independent, toolbar reflects the current text, and page scroll is
   independent. Switch to another notebook tab and back.
4. Try typing several words in Notes 1, then Notes 2; Undo/Redo each edit and
   ensure the text change affects its **original** notes page only.
5. Rename Notes 2 and Undo/Redo; remove Notes 2 with the minus button and
   verify Undo restores it with exact content and formatting.
6. Adjust one notes page's Page Setup; check it does not alter the others.
7. Save, close, reopen; ensure the active notes page, names, contents,
   formatting, links, view state and page setup are all preserved.
8. Move some PDF pages within a group, and confirm existing note links still
   resolve via the original stable PDF page IDs.
9. Test during autosave and after switching to a different notebook tab.

## D. Regression smoke test
- Test PDF import and Smart Import (bookmarks, collapse, [chapter] labels).
- Test thumbnail scrolling with 100+ pages, annotation tools, OCR and text
  editing controls; check reading rewards/Playful theme and Crisp preview.
- Confirm no new Qt `object already deleted` tracebacks or silent errors.

If Windows reports any crash or lost formatting, retain the old notebook and
send a traceback plus exact steps; do not overwrite the known-good copy.
