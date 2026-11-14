"""Small, theme-inheriting Qt dialogs for document and paragraph spacing."""
from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QDoubleSpinBox,
                               QDialogButtonBox, QLabel)
from .notes_layout import NotesPageSetup


def point_input(value: float, *, high: float = 288.0, step: float = 3.0):
    spin = QDoubleSpinBox()
    spin.setRange(0, high)
    spin.setDecimals(2)
    spin.setSingleStep(step)
    spin.setSuffix(' pt')
    spin.setValue(value)
    return spin


class NotesPageSetupDialog(QDialog):
    """Edit page margins and text layout without touching the source PDFs."""
    def __init__(self, setup: NotesPageSetup, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Notes page setup')
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        intro = QLabel('Document margins are saved per project. In a narrow notes column, '
                       'their on-screen display adapts to leave room for reading.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.top = point_input(setup.top_pt)
        self.bottom = point_input(setup.bottom_pt)
        self.left = point_input(setup.left_pt)
        self.right = point_input(setup.right_pt)
        form.addRow('Top margin', self.top)
        form.addRow('Bottom margin', self.bottom)
        form.addRow('Left margin', self.left)
        form.addRow('Right margin', self.right)
        self.line = QDoubleSpinBox()
        self.line.setDecimals(2)
        self.line.setRange(1.0, 3.0)
        self.line.setSingleStep(0.05)
        self.line.setValue(setup.line_spacing)
        self.line.setSuffix(' ×')
        form.addRow('Default line spacing', self.line)
        self.after = point_input(setup.paragraph_after_pt, high=72, step=1)
        form.addRow('Paragraph space after', self.after)
        layout.addLayout(form)
        footnote = QLabel('Defaults: 72 pt (1 inch) margins, 1.15× lines, and 8 pt after '
                          'a normal paragraph at 13 pt. List items have no gap until '
                          'the final item, which gets the normal paragraph gap.')
        footnote.setWordWrap(True)
        layout.addWidget(footnote)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._previous = setup

    def result_setup(self):
        return NotesPageSetup(top_pt=self.top.value(), bottom_pt=self.bottom.value(),
                              left_pt=self.left.value(), right_pt=self.right.value(),
                              line_spacing=self.line.value(), paragraph_after_pt=self.after.value(),
                              base_font_pt=self._previous.base_font_pt)


class ParagraphSpacingDialog(QDialog):
    """Translate familiar line/paragraph spacing controls into Qt formats."""
    def __init__(self, before_pt: float, after_pt: float, line_spacing: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Paragraph spacing')
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.before = point_input(before_pt, high=72, step=1)
        self.after = point_input(after_pt, high=72, step=1)
        self.line = QDoubleSpinBox()
        self.line.setRange(1.0, 3.0)
        self.line.setDecimals(2)
        self.line.setSingleStep(0.05)
        self.line.setValue(line_spacing)
        self.line.setSuffix(' ×')
        form.addRow('Space before', self.before)
        form.addRow('Space after', self.after)
        form.addRow('Line spacing', self.line)
        layout.addLayout(form)
        tip = QLabel('Applies only to the current paragraph or paragraphs you selected.')
        tip.setWordWrap(True)
        layout.addWidget(tip)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
