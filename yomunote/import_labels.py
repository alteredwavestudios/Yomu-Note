"""Import label presets independent of the internal PDF asset name.

The original filename is display metadata.  It must never be used as an
on-disk path or as a Python format string supplied by a document.
"""
from __future__ import annotations

import re

FORMATS = {
    'filename_page': ('Filename · Page 1', '{filename} · Page {n}'),
    'page': ('Page 1', 'Page {n}'),
    'number': ('1', '{n}'),
    'slide': ('Slide 1', 'Slide {n}'),
    'chapter': ('Chapter 1', 'Chapter {n}'),
    'filename_number': ('Filename · 1', '{filename} · {n}'),
    'number_filename': ('1 · Filename', '{n} · {filename}'),
    'filename_chapter': ('Filename · Chapter 1', '{filename} · Chapter {n}'),
    'filename_slide': ('Filename · Slide 1', '{filename} · Slide {n}'),
    'section': ('Section 1', 'Section {n}'),
    'figure': ('Figure 1', 'Figure {n}'),
    'sheet': ('Sheet 1', 'Sheet {n}'),
    'page_of_total': ('Page 1 of 12', 'Page {n} of {total}'),
    'slide_of_total': ('Slide 1 of 12', 'Slide {n} of {total}'),
    'page_abbrev': ('p. 1', 'p. {n}'),
    'page_padded': ('Page 001', 'Page {n3}'),
    'roman': ('Page i, ii, iii…', 'Page {roman_lower}'),
    'roman_upper': ('Page I, II, III…', 'Page {roman}'),
    'custom': ('Custom pattern…', ''),
}

# Both {chapter} and the more discoverable [chapter] syntax are accepted.
# Only these whitelisted fields are substituted; no arbitrary formatting.
_TOKEN_NAMES = (r'filename|n|n2|n3|page|slide|chapter|section|total|'
                r'roman|roman_lower')
_TOKEN = re.compile(
    rf'(?:\{{(?P<brace>{_TOKEN_NAMES})\}}|\[(?P<square>{_TOKEN_NAMES})\])')
_NUMBER_FIELDS = frozenset(('n', 'page', 'n2', 'n3', 'roman', 'roman_lower',
                            'slide', 'chapter', 'section'))


def uses_chapter_token(pattern):
    """The chapter marker requires final review boundaries before labelling."""
    return isinstance(pattern, str) and any(
        (match.group('brace') or match.group('square')) == 'chapter'
        for match in _TOKEN.finditer(pattern))


def to_roman(number):
    """Return conventional Roman numerals for imported page indices."""
    values = [(1000, 'M'), (900, 'CM'), (500, 'D'),
              (400, 'CD'), (100, 'C'), (90, 'XC'), (50, 'L'),
              (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'),
              (4, 'IV'), (1, 'I')]
    result = []
    for magnitude, symbol in values:
        repetitions, number = divmod(number, magnitude)
        result.append(symbol * repetitions)
    return ''.join(result)



def make_title(filename, index, total, preset='filename_page', custom='', *, chapter=1):
    """Format a visible label using a deliberately small token grammar.

    We replace approved placeholders ourselves rather than calling
    str.format on uncontrolled input.  Curly braces and other characters
    from an academic article filename remain ordinary literal text.
    """
    if not isinstance(filename, str) or len(filename) > 4096:
        raise ValueError('Invalid source filename.')
    if not isinstance(index, int) or not 1 <= index <= 20_000:
        raise ValueError('Invalid source page number.')
    if not isinstance(total, int) or not index <= total <= 20_000:
        raise ValueError('Invalid page count.')
    if preset not in FORMATS:
        raise ValueError('Unknown page label format.')
    if type(chapter) is not int or not 1 <= chapter <= 20_000:
        raise ValueError('Invalid reviewed chapter number.')
    pattern = custom if preset == 'custom' else FORMATS[preset][1]
    if not isinstance(pattern, str) or not 1 <= len(pattern) <= 160:
        raise ValueError('Custom label must have 1–160 characters.')
    if (preset == 'custom' and not any(
            (match.group('brace') or match.group('square')) in _NUMBER_FIELDS
            for match in _TOKEN.finditer(pattern))):
        raise ValueError('A custom label needs a numbering token such as [page] or [chapter].')
    values = {'filename': filename, 'n': str(index),
              'n2': f'{index:02d}', 'n3': f'{index:03d}',
              'roman': to_roman(index),
              'roman_lower': to_roman(index).lower(),
              'page': str(index), 'slide': str(index),
              'chapter': str(chapter), 'section': str(index),
              'total': str(total)}
    title = _TOKEN.sub(
        lambda match: values[match.group('brace') or match.group('square')],
        pattern).strip()
    if not title or len(title) > 8192:
        raise ValueError('Page label is empty or too long.')
    return title


def label_imported_pages(pages, filename, preset, custom='', *, chapter_numbers=None):
    """Modify only labels, keeping the immutable source-page indices intact.

    chapter_numbers comes from the user's APPROVED outline. Without an
    outline, the document is treated as a single chapter for labelling.
    """
    count = len(pages)
    if chapter_numbers is None:
        chapter_numbers = [1] * count
    if len(chapter_numbers) != count:
        raise ValueError('Chapter numbers do not match the imported pages.')
    for i, (page, number) in enumerate(zip(pages, chapter_numbers), 1):
        page['title'] = make_title(filename, i, count, preset, custom,
                                   chapter=number)
    return pages


def relabel_reviewed_chapters(batches, sections_by_file, pattern, *, combined=False):
    """Resolve [chapter] against final user-approved headings, not raw PDF TOC.

    Runs only on staged pages *after* review and before committing a plan.
    The number is the 1-based ordinal of a level-1 heading in each file;
    nested subsections do not increment it. A file with no headings has one
    implicit chapter. Other page tokens keep their previous numbering rules.
    """
    if len(batches) != len(sections_by_file):
        raise ValueError('The chapter outline no longer matches the imported files.')
    from .import_structure import chapter_numbers_for_pages

    if combined:
        total = sum(len(pages) for _name, pages in batches)
        ordinal = 0
        for (name, pages), headings in zip(batches, sections_by_file):
            numbers = chapter_numbers_for_pages(len(pages), headings)
            for page, chapter in zip(pages, numbers):
                ordinal += 1
                page['title'] = make_title(name, ordinal, total, 'custom',
                                           pattern, chapter=chapter)
    else:
        for (name, pages), headings in zip(batches, sections_by_file):
            label_imported_pages(pages, name, 'custom', pattern,
                chapter_numbers=chapter_numbers_for_pages(len(pages), headings))
