"""Smart Import's *explicit* destination and grouping choices.

No more duplicate 'create a group' checkbox + 'one group per file' dropdown.
The live PDF preview page is deliberately not consulted for destination.
"""
from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QLineEdit, QSpinBox, QVBoxLayout,
)

from .import_labels import FORMATS, make_title
from .importers import IMAGE_EXTS


class ImportOptionsDialog(QDialog):
    """Collect import preferences before reading/committing source pages.

    A checked checkbox in this dialog is a REQUEST, not a live edit. The
    importer builds a plan and only commits it after validation succeeds.
    """
    def __init__(self, parent=None, *, smart=False, file_count=1,
                 target_group=None, destination_groups=(), preset='filename_page',
                 custom='{filename} · Page {n}', files=(),
                 collapse_new_groups=True):
        super().__init__(parent)
        self.setWindowTitle('Smart Import — organise files' if smart else 'Import pages')
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        introduction = QLabel('Choose a destination and how to organise your source files. '
                              'You can review and correct detected chapters before importing.')
        introduction.setWordWrap(True)
        layout.addWidget(introduction)
        form = QFormLayout()
        self.destination = QComboBox()
        self.destination.addItem('Root of this tab (outside existing groups)', None)
        for group_id, label in destination_groups:
            self.destination.addItem(label, group_id)
        selected = self.destination.findData(target_group)
        self.destination.setCurrentIndex(max(0, selected))
        form.addRow('Import into:', self.destination)

        self.group_mode = QComboBox()
        self.group_mode.addItem('One group for each source file', 'per_file')
        self.group_mode.addItem('One group containing all source files', 'combined')
        self.group_mode.addItem('No new file groups (pages into destination)', 'none')
        images = (file_count > 1 and files and all(
            Path(f).suffix.lower() in IMAGE_EXTS for f in files))
        self.group_mode.setCurrentIndex(1 if smart and images else 0 if smart else 2)
        form.addRow('Organise files:', self.group_mode)
        self.collapse_groups = QCheckBox('Collapse all newly imported groups and subgroups')
        self.collapse_groups.setChecked(bool(collapse_new_groups))
        self.collapse_groups.setToolTip(
            'Only newly created folders are affected; existing folders retain their state.')
        form.addRow('Initial group visibility:', self.collapse_groups)

        self.structure = QComboBox()
        self.structure.addItem('Automatic — reliable embedded bookmarks', 'auto')
        self.structure.addItem('PDF bookmarks / converted document outline', 'bookmarks')
        self.structure.addItem('Every N pages (manual divisions)', 'ranges')
        self.structure.addItem('Do not create chapter subgroups', 'none')
        form.addRow('Create subgroups by:', self.structure)
        self.depth = QSpinBox()
        self.depth.setRange(1, 3)
        self.depth.setValue(2)
        self.depth.setSuffix(' outline levels')
        form.addRow('Detected structure depth:', self.depth)
        self.interval = QSpinBox()
        self.interval.setRange(1, 500)
        self.interval.setValue(20)
        self.interval.setSuffix(' pages')
        form.addRow('Fixed-range interval:', self.interval)

        self.group_name = QLineEdit()
        self.group_name.setMaxLength(120)
        self.group_name.setPlaceholderText('Leave blank to use original filename')
        form.addRow('Group name (optional):', self.group_name)

        self.preset = QComboBox()
        for key, (label, _pattern) in FORMATS.items():
            self.preset.addItem(label, key)
        self.preset.setCurrentIndex(max(0, self.preset.findData(preset)))
        form.addRow('Page labels:', self.preset)
        self.custom = QLineEdit(custom)
        self.custom.setPlaceholderText('e.g. {filename} — {n} of {total}')
        form.addRow('Custom label pattern:', self.custom)
        layout.addLayout(form)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)
        help_line = QLabel('Custom tokens accept either [page] or {page} syntax. '
                           '[chapter] means the numbered top-level chapter AFTER you review its boundaries; '
                           '[page] means the page number. Chapter numbering resets for each source file; '
                           'front matter and files without chapters use 1. '
                           'Other tokens: [filename], [n], [slide], [total], [n2], [n3], [roman]. '
                           '[section] is currently a page-index alias, not subsection numbering.')
        help_line.setWordWrap(True)
        layout.addWidget(help_line)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Continue')
        layout.addWidget(self.buttons)
        self.buttons.accepted.connect(self._accept_valid)
        self.buttons.rejected.connect(self.reject)
        self.preset.currentIndexChanged.connect(self._update)
        self.custom.textChanged.connect(self._update)
        self.group_mode.currentIndexChanged.connect(self._update)
        self.structure.currentIndexChanged.connect(self._update)
        self._file_count = file_count
        self._update()

    def _update(self, *_):
        is_custom = self.preset.currentData() == 'custom'
        self.custom.setEnabled(is_custom)
        mode = self.group_mode.currentData()
        structure_allowed = mode != 'none'
        self.structure.setEnabled(structure_allowed)
        self.collapse_groups.setEnabled(structure_allowed)
        self.interval.setEnabled(structure_allowed and self.structure.currentData() == 'ranges')
        self.depth.setEnabled(structure_allowed and self.structure.currentData() in ('auto', 'bookmarks'))
        self.group_name.setEnabled(mode == 'combined' or
                                   (mode == 'per_file' and self._file_count == 1))
        try:
            title = make_title('Example document', 2, 12,
                               self.preset.currentData(), self.custom.text())
        except ValueError as exc:
            self.preview.setText(str(exc))
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        else:
            self.preview.setText('Page label preview: ' + title + '\n'
                + ('A second screen lets you review every proposed chapter and page boundary.'
                   if structure_allowed else 'Pages will go directly into the selected destination.'))
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    def _accept_valid(self):
        try:
            make_title('Example document', 1, 1,
                       self.preset.currentData(), self.custom.text())
        except ValueError:
            return
        self.accept()

    def options(self):
        mode = self.group_mode.currentData()
        return dict(smart_import=mode != 'none',
                    smart_group_mode=mode,
                    structure_mode=self.structure.currentData() if mode != 'none' else 'none',
                    page_interval=self.interval.value(),
                    max_subgroup_depth=self.depth.value(),
                    group_id=self.destination.currentData(),
                    label_format=self.preset.currentData(),
                    custom_format=self.custom.text(),
                    group_label=self.group_name.text().strip()[:120],
                    collapse_new_groups=self.collapse_groups.isChecked())
