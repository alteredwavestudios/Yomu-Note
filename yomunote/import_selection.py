"""Smart Import 3.0: safe, physical-page selection before a single commit.

All numbering here is the original *one-based source page* position, not the
number printed on a textbook. This module uses Python only and never modifies
Project.pages, the original staged page dictionaries or Qt state.
"""
from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from copy import deepcopy

from .import_structure import validate_sections

MAX_SELECTION_PAGES = 20_000
_RANGE = re.compile(r'\s*(\d+)\s*(?:[-–]\s*(\d+)\s*)?\Z')


def parse_page_ranges(text: str, page_count: int) -> list[int]:
    """Read e.g. '1-5, 9, 12–14' into sorted unique *physical* page numbers.

    Empty input is invalid (the GUI has an explicit All pages toggle); malformed,
    descending or out-of-bounds ranges fail instead of silently losing pages.
    """
    if type(page_count) is not int or not 1 <= page_count <= MAX_SELECTION_PAGES:
        raise ValueError('Invalid source page count.')
    if not isinstance(text, str) or len(text) > 10_000 or not text.strip():
        raise ValueError('Enter a page range, such as 1-10, 15, 20-25.')
    chosen = set()
    chunks = text.split(',')
    if len(chunks) > MAX_SELECTION_PAGES:
        raise ValueError('Too many page ranges.')
    for chunk in chunks:
        match = _RANGE.fullmatch(chunk)
        if not match:
            raise ValueError(f'Invalid page range: {chunk.strip()[:55]!r}. Use 1-10, 15, 20-25.')
        first = int(match.group(1))
        last = int(match.group(2)) if match.group(2) else first
        if not 1 <= first <= last <= page_count:
            raise ValueError(f'Page range {first}-{last} must be within 1-{page_count}.')
        chosen.update(range(first, last + 1))
    return sorted(chosen)


def heading_page_bounds(sections: list[dict], page_count: int) -> list[tuple[int, int]]:
    """Inclusive source-page interval for each heading *and its descendants*."""
    headings = validate_sections(deepcopy(sections), page_count)
    bounds = []
    for index, heading in enumerate(headings):
        end = page_count
        for later in headings[index + 1:]:
            if later['level'] <= heading['level']:
                end = later['start'] - 1
                break
        bounds.append((heading['start'], end))
    return bounds


def select_source_pages(page_count: int, sections: list[dict], *,
                        page_range: list[int] | None = None,
                        section_enabled: list[bool] | None = None,
                        include_frontmatter: bool = True) -> list[int]:
    """Intersect page-range and bookmark choices without duplicating pages.

    A checkbox controls the pages directly under *its* heading. Parent toggles
    are propagated to descendants by the GUI, but an unchecked subsection may
    be omitted while the parent's introductory pages are kept. A checked
    subsection can also be chosen alone. Pages before the first heading have
    their own inclusion switch.
    """
    headings = validate_sections(deepcopy(sections), page_count)
    if section_enabled is None:
        section_enabled = [True] * len(headings)
    if len(section_enabled) != len(headings) or any(type(x) is not bool for x in section_enabled):
        raise ValueError('Chapter selection no longer matches the reviewed outline.')
    if page_range is None:
        page_range = list(range(1, page_count + 1))
    if any(type(n) is not int or n < 1 or n > page_count for n in page_range):
        raise ValueError('Selected page is outside the source document.')
    allowed = set(page_range)
    selected = []
    next_heading = 0
    stack = []
    for number in range(1, page_count + 1):
        while next_heading < len(headings) and headings[next_heading]['start'] == number:
            level = headings[next_heading]['level']
            while len(stack) >= level:
                stack.pop()
            stack.append(next_heading)
            next_heading += 1
        on = section_enabled[stack[-1]] if stack else include_frontmatter
        if on and number in allowed:
            selected.append(number)
    return selected


def remap_selected_sections(sections: list[dict], source_page_count: int,
                            selected_pages: list[int]) -> list[dict]:
    """Retain nonempty chapter groups and remap starts into filtered page order.

    A chapter surviving only through a selected subsection stays as its parent;
    empty siblings disappear. A selected first page midway through a chapter
    becomes that chapter's first page, with no fabricated page references.
    """
    headings = validate_sections(deepcopy(sections), source_page_count)
    numbers = sorted(set(selected_pages))
    if any(type(n) is not int or n < 1 or n > source_page_count for n in numbers):
        raise ValueError('Selected page is outside the source document.')
    filtered = []
    for heading, (first, last) in zip(headings, heading_page_bounds(headings, source_page_count)):
        first_index = bisect_left(numbers, first)
        if first_index == len(numbers) or numbers[first_index] > last:
            continue
        # Every ancestor that contains this page is also retained, so the
        # outline depth stays contiguous even after omitting entire chapters.
        filtered.append({**heading, 'start': first_index + 1})
    if numbers:
        return validate_sections(filtered, len(numbers))
    return []


def filter_staged_import(batches, sections_by_file, selected_numbers_by_file):
    """Return (retained batches, remapped sections, omitted pages) without mutation.

    Empty source files are simply omitted; an entirely empty selection is an
    error. Omitted pages must only have their source assets cleaned *after*
    successful commit, since selected pages may share the same PDF original.
    """
    if not len(batches) == len(sections_by_file) == len(selected_numbers_by_file):
        raise ValueError('Source selection no longer matches staged documents.')
    retained, remapped, omitted = [], [], []
    for (name, pages), headings, numbers in zip(batches, sections_by_file, selected_numbers_by_file):
        if not pages:
            raise ValueError('Cannot filter an empty source.')
        if len(set(numbers)) != len(numbers) or sorted(numbers) != list(numbers):
            raise ValueError('Selected pages must appear once in source order.')
        if any(type(n) is not int or n < 1 or n > len(pages) for n in numbers):
            raise ValueError('Selected page is outside the source document.')
        keep = set(numbers)
        accepted = [page for i, page in enumerate(pages, 1) if i in keep]
        dropped = [page for i, page in enumerate(pages, 1) if i not in keep]
        if accepted:
            retained.append((name, accepted))
            remapped.append(remap_selected_sections(headings, len(pages), numbers))
        if dropped:
            omitted.append((name, dropped))
    if not retained:
        raise ValueError('Select at least one page to import.')
    return retained, remapped, omitted
