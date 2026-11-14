"""Serializable page setup and paragraph measurements for Qt's native text engine.

Qt QTextBlock/QTextList objects remain the source of truth for paragraphs and
list membership.  This module stores only document-wide defaults; paragraph
exceptions are real QTextBlockFormat properties inside the saved notes HTML.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import math


@dataclass(frozen=True)
class NotesPageSetup:
    """Document-wide values in typographic points (72 points per inch)."""

    top_pt: float = 72.0
    bottom_pt: float = 72.0
    left_pt: float = 72.0
    right_pt: float = 72.0
    line_spacing: float = 1.15
    # Eight points is the desired paragraph gap at the original 13-point base.
    paragraph_after_pt: float = 8.0
    base_font_pt: float = 13.0
    list_step_pt: float = 18.0       # 0.25 inch at each nesting depth.
    list_first_text_pt: float = 36.0  # 0.5 inch from the document margin.

    def __post_init__(self):
        for name in ('top_pt', 'bottom_pt', 'left_pt', 'right_pt'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 288:
                raise ValueError(f'Invalid page margin: {name}')
        for name, low, high in (('line_spacing', 1.0, 3.0),
                                ('paragraph_after_pt', 0.0, 72.0),
                                ('base_font_pt', 7.0, 120.0)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'Invalid page setup value: {name}')
        if self.list_step_pt != 18 or self.list_first_text_pt != 36:
            raise ValueError('List geometry must follow the quarter-inch grid.')

    def after_for_font(self, point_size: float) -> float:
        """Scale the baseline 8pt gap when the document's default font changes."""
        return round(self.paragraph_after_pt * max(7.0, point_size) / self.base_font_pt, 3)

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value) -> 'NotesPageSetup':
        if not isinstance(value, dict):
            raise ValueError('Page setup must be an object.')
        allowed = set(cls.__dataclass_fields__)
        if set(value) - allowed:
            raise ValueError('Unknown page setup fields.')
        return cls(**value)


def pt_to_px(points: float, dpi: float) -> float:
    """Convert points to Qt layout pixels at the current display's logical DPI."""
    return float(points) * max(72.0, float(dpi)) / 72.0


def fitted_margins(setup: NotesPageSetup, dpi: float, viewport_width: int,
                   minimum_text_width: float = 148) -> tuple[float, float, float, float]:
    """Responsive *view* geometry: keep notes legible in a narrow splitter pane.

    The saved page setup always retains its real 72pt margins.  Only the live
    onscreen layout shrinks side margins if the notes column is unusually small.
    """
    top = pt_to_px(setup.top_pt, dpi)
    bottom = pt_to_px(setup.bottom_pt, dpi)
    left = pt_to_px(setup.left_pt, dpi)
    right = pt_to_px(setup.right_pt, dpi)
    available = max(0.0, float(viewport_width) - minimum_text_width)
    if left + right > available and left + right > 0:
        factor = available / (left + right)
        left *= factor
        right *= factor
    return top, bottom, left, right
