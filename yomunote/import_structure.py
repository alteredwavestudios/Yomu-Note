"""Smart Import 2.0: inspect document navigation without rasterising pages.

The *real* page index is authoritative. A PDF bookmark title may call its page
"17" even when that bookmark points to actual PDF page 23. All positions in
this module are 1-based **physical document pages**, never printed page labels.

No Qt imports, project mutations, OCR, network, or optional dependencies.
PDFium access shares the application's one global lock with thumbnails/OCR.
This lets the editor and tests use the exact same validated section plan.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .page_groups import MAX_DEPTH, group_node, page_node
from .pdfium_guard import PDFIUM_LOCK

MAX_DETECTED_HEADINGS = 300  # protect a huge per-page bookmark tree
MAX_IMPORT_DEPTH = 3         # keep imported outlines navigable in a narrow rail


def validate_sections(sections, page_count, *, max_depth=MAX_IMPORT_DEPTH):
    """Return clean sections or raise BEFORE modifying the live notebook.

    Every section has title, level (1-based), and start (physical page number).
    Sections form a document-ordered outline. A child may start on exactly the
    same page as its parent. Sibling sections must not have identical starts.
    Missing or ambiguous ranges never cause page loss: ungrouped leaves remain.
    """
    if not isinstance(page_count, int) or isinstance(page_count, bool) or not 1 <= page_count <= 20_000:
        raise ValueError('Invalid source page count.')
    if not isinstance(sections, list) or len(sections) > MAX_DETECTED_HEADINGS:
        raise ValueError('Too many proposed chapter headings.')
    result = []
    previous_start = 0
    stack = []
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError('Invalid chapter entry.')
        title = section.get('title')
        start = section.get('start')
        level = section.get('level')
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
            raise ValueError('Chapter names must contain 1–120 characters.')
        if type(start) is not int or not 1 <= start <= page_count:
            raise ValueError('A chapter must start on a page in its source file.')
        if type(level) is not int or not 1 <= level <= max_depth:
            raise ValueError(f'Chapter depth must be between 1 and {max_depth}.')
        if level > len(stack) + 1:
            raise ValueError('A chapter cannot skip a hierarchy level.')
        if start < previous_start:
            raise ValueError('Chapter starts must follow source page order.')
        while len(stack) >= level:
            stack.pop()
        # No two siblings may start on the same physical page: one would be
        # empty. An ancestor and its first child MAY start together.
        if result and start == previous_start and level <= result[-1]['level']:
            raise ValueError('Two adjacent chapters would start on the same page.')
        clean = {'title': title.strip(), 'start': start, 'level': level,
                 'origin': str(section.get('origin', 'Manual'))[:50]}
        result.append(clean)
        stack.append(clean)
        previous_start = start
    return result


def extract_pdf_outline(path: Path, *, max_depth=MAX_IMPORT_DEPTH):
    """Get PDF bookmark destinations; return (page_count, sections, warnings).

    Broken/non-monotonic entries are skipped, NOT reshuffled: reordering could
    quietly attach textbook pages to the wrong chapter. When an outline is
    absent or unreliable the preview lets people create their own sections.
    """
    import pypdfium2 as pdfium

    path = Path(path)
    with PDFIUM_LOCK:
        document = pdfium.PdfDocument(str(path))
        try:
            count = len(document)
            if not 1 <= count <= 20_000:
                raise ValueError('PDF has an unsupported page count.')
            sections = []
            warnings = []
            previous_start = 0
            # Convert PDFium's zero-based bookmark depths into a contiguous
            # hierarchy only when an actual destination was retained.
            levels = []
            for bookmark in document.get_toc(max_depth=16):
                if len(sections) >= MAX_DETECTED_HEADINGS:
                    # A partial outline would label the rest of this book as
                    # the final chapter. Refuse to guess: review it manually.
                    return count, [], ['Too many bookmarks for automatic grouping; please create sections manually.']
                destination = bookmark.get_dest()
                index = destination.get_index() if destination else None
                if index is None or index < 0 or index >= count:
                    continue
                title = ' '.join(bookmark.get_title().split())[:120]
                if not title:
                    continue
                start = index + 1
                if start < previous_start:
                    warnings.append('Out-of-order bookmarks were skipped; review chapter boundaries.')
                    continue
                raw_level = bookmark.level
                while levels and levels[-1] >= raw_level:
                    levels.pop()
                level = min(len(levels) + 1, max_depth)
                # Beyond the requested maximum depth, do not create siblings
                # for every microscopic bookmark. Keep the shallow hierarchy.
                if bookmark.level >= max_depth:
                    continue
                if sections and start == previous_start and level <= sections[-1]['level']:
                    warnings.append('Duplicate-page bookmarks were skipped.')
                    continue
                section = {'title': title, 'start': start, 'level': level,
                           'origin': 'PDF bookmark'}
                try:
                    validate_sections(sections + [section], count)
                except ValueError:
                    warnings.append('Ambiguous bookmarks were skipped.')
                    continue
                sections.append(section)
                levels.append(raw_level)
                previous_start = start
            return count, sections, list(dict.fromkeys(warnings))
        finally:
            document.close()


def detected_structure(project, pages):
    """Inspect the already indexed source (including converted PDFs).

    This runs in the import worker after its files are staged but BEFORE the
    notebook or Undo history are changed. Converted Office/EPUB PDFs are used
    only when their converter retained valid PDF bookmarks. We deliberately
    do not guess DOCX/EPUB source headings' PDF page numbers.
    """
    if not pages:
        raise ValueError('Cannot inspect an empty source.')
    count = len(pages)
    if pages[0].get('kind') != 'pdf':
        return {'page_count': count, 'sections': [], 'warnings': [],
                'source': 'Images / no document outline'}
    render_source = pages[0].get('render_source')
    try:
        actual_count, sections, warnings = extract_pdf_outline(
            project.asset_path(render_source))
        if actual_count != count:
            return {'page_count': count, 'sections': [],
                    'warnings': ['Document outline page count did not match imported pages.'],
                    'source': 'Unavailable'}
    except Exception as exc:
        return {'page_count': count, 'sections': [],
                'warnings': [f'Could not read outline: {exc}'], 'source': 'Unavailable'}
    return {'page_count': count, 'sections': sections, 'warnings': warnings,
            'source': 'PDF bookmarks' if sections else 'No usable embedded bookmarks'}


def fixed_range_sections(page_count: int, step=20):
    if type(step) is not int or not 1 <= step <= 500:
        raise ValueError('Page interval must be between 1 and 500.')
    if (page_count + step - 1) // step > MAX_DETECTED_HEADINGS:
        raise ValueError('Too many fixed ranges. Choose a larger page interval.')
    return [{'title': f'Pages {start}–{min(page_count, start + step - 1)}',
             'level': 1, 'start': start, 'origin': 'Fixed page range'}
            for start in range(1, page_count + 1, step)]


def chapter_numbers_for_pages(page_count, sections):
    """Return 1-based chapter numbers from approved top-level headings.

    Subsection (level 2/3) boundaries do not increment the chapter count.
    Any front matter before the first heading, or an unstructured document,
    uses chapter 1 rather than an unexpected 'Chapter 0'. This maps titles
    only; it cannot alter grouping, page IDs, or the actual PDF page number.
    """
    headings = validate_sections(deepcopy(sections), page_count)
    numbers = []
    chapter = 0
    next_heading = 0
    for page in range(1, page_count + 1):
        while (next_heading < len(headings) and
               headings[next_heading]['start'] == page):
            if headings[next_heading]['level'] == 1:
                chapter += 1
            next_heading += 1
        numbers.append(max(1, chapter))
    return numbers


def section_tree(page_ids, sections, *, collapsed=False):
    """Create a fresh grouping tree retaining EVERY page exactly once.

    A page lies at its deepest active heading, or is a bare page before the
    first heading. Parent groups aggregate their children's pages without
    duplicating references. Zero groups returns the original flat leaves.
    """
    page_ids = list(page_ids)
    headings = validate_sections(deepcopy(sections), len(page_ids))
    roots = []
    current = []
    section_index = 0
    for number, page_id in enumerate(page_ids, start=1):
        while section_index < len(headings) and headings[section_index]['start'] == number:
            heading = headings[section_index]
            while len(current) >= heading['level']:
                current.pop()
            node = group_node(heading['title'], collapsed=collapsed)
            target = current[-1]['children'] if current else roots
            target.append(node)
            current.append(node)
            section_index += 1
        (current[-1]['children'] if current else roots).append(page_node(page_id))
    return roots
