# How Page Groups Work (Beginner's Guide)

Yomu Note contains two different ideas:

- A **page** is the PDF page, slide, or picture you read.
- A **group** is a named folder that organises pages.

The actual pages are stored in the familiar flat reading order:

```python
project.pages = [page1, page2, page3]
```

A group stores only references to those pages:

```python
project.page_groups = [
    {
        "type": "group",
        "id": "a unique identifier",
        "name": "Week One",
        "collapsed": False,
        "children": [
            {"type": "page", "page_id": "page-one-id"},
            {"type": "page", "page_id": "page-two-id"},
        ],
    },
]
```

In real notebooks the IDs are long hexadecimal strings.
They let the app refer to a page even if it is renamed.

## Where to start reading the source

1. `yomunote/page_groups.py` is the data model.
   It contains no GUI code and has tests for its safety rules.
2. `yomunote/page_groups_ui.py` is the Qt tree widget.
   It draws the folders and sends events when the user clicks.
3. `yomunote/window.py` connects the widget to a notebook.
   Search for `_commit_group_edit` and `_apply_group_snapshot`.
4. `yomunote/project.py` loads and saves the hierarchy in
   the existing project JSON manifest.

## Why we validate before changing anything

A group should never own the only copy of a page.
Each live page must appear exactly once in the hierarchy.

For example, if a drag accidentally places the same page
in two different folders, validation rejects that move.

## What Undo means

An **Undo transaction** remembers the earlier state.
Yomu Note records the old and new tree and page order.
One Undo restores both together.

We do NOT save historical Undo snapshots to notebook files.
The current saved notebook contains only the live pages.

## Why no new PDF renderer was needed

The existing preview engine uses `Project.pages`.
It never needs to know whether a folder is collapsed.
That also means old page-navigation shortcuts keep working.

Comments in the new Python files use short, wrapped lines
so you can read them in a narrow code editor.


## v0.7.0a — Why reading and selection use different colours

The selected items are the pages you are organising.
For example, you might select three pages to move together.

The active page is what you are currently reading.
Its accent stripe moves when you use page navigation shortcuts.
The two are not the same thing, so neither changes the other.

Qt can sometimes replace an item when you drag it.
We therefore remember its page ID, not the old item object.
This avoids trying to use a deleted Qt object.

## Why page thumbnails are loaded only when visible

A large book can contain hundreds of pages.
Keeping a full image for each page would use far too much memory.

The Groups view asks for at most twenty visible thumbnails.
The image files are shared with the original Thumbnails view.
When a page scrolls away, its icon is removed from memory.

## Why imports need a group destination

Previously, a newly inserted page could fall between two pages
inside the same group. The compatibility code then guessed
that this new page belonged to their group.

A root-level import should not depend on that coincidence.
Now the importer chooses the target first and then organises
the added page IDs explicitly, without duplicating PDFs.
