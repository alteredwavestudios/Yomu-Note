"""Small native Qt selection dialog for importing/exporting complete study tabs.

No tree reconstruction happens when a checkbox changes. The source is an
immutable inspection result, not a live notebook or an editable widget model.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout,
                               QHBoxLayout)


def readable_bytes(count):
    if count < 1024:
        return f'{count} B'
    if count < 1024 * 1024:
        return f'{count / 1024:.1f} KiB'
    if count < 1024 ** 3:
        return f'{count / 1024 ** 2:.1f} MiB'
    return f'{count / 1024 ** 3:.2f} GiB'


class TabExchangeDialog(QDialog):
    """Simple checklist for picking which complete tabs to share.

    Display rows represent *metadata*, not live project widgets. Checking
    a box cannot accidentally modify the source notebook; selected IDs are
    returned only after the user confirms the dialog.
    """
    def __init__(self, tabs, *, action='import', source_name='',
                 preselect=(), parent=None):
        super().__init__(parent)
        self.tabs = tuple(tabs)
        self.action = action
        self.setWindowTitle('Import Tabs from Notebook' if action == 'import'
                            else 'Export Selected Tabs')
        self.setMinimumWidth(515)
        layout = QVBoxLayout(self)
        heading = QLabel('Choose the complete tabs to ' + action + ':')
        layout.addWidget(heading)
        if source_name:
            source = QLabel(str(source_name))
            source.setWordWrap(True)
            layout.addWidget(source)
        self.list = QListWidget(self)
        self.list.setAlternatingRowColors(True)
        self.list.setAccessibleName('Notebook tab selection')
        chosen = set(preselect)
        for tab in self.tabs:
            item = QListWidgetItem(
                f'{tab.title}   ·   {tab.pages:,} pages   ·   '
                f'{tab.notes_pages:,} notes pages   ·   {readable_bytes(tab.bytes)}')
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(Qt.ItemDataRole.UserRole, tab.id)
            item.setCheckState(Qt.CheckState.Checked if (
                tab.id in chosen or (not chosen and action == 'import'))
                else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        layout.addWidget(self.list)
        select_row = QHBoxLayout()
        all_button = QPushButton('Select All')
        none_button = QPushButton('Select None')
        select_row.addWidget(all_button)
        select_row.addWidget(none_button)
        select_row.addStretch()
        layout.addLayout(select_row)
        all_button.clicked.connect(lambda: self._set_all(True))
        none_button.clicked.connect(lambda: self._set_all(False))
        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        privacy = QLabel(
            'A shared tab contains its original documents, annotations and '
            'rich-text notes. Private preferences, deleted files and recovery '
            'backups are excluded.')
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        self.confirm = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.confirm.setText('Import Selected Tabs' if action == 'import'
                             else 'Export Selected Tabs')
        layout.addWidget(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.list.itemChanged.connect(self._refresh)
        self._refresh()

    def _set_all(self, enabled):
        """Change many checkboxes without running the summary 256 times.

        ``setCheckState`` normally emits itemChanged for EACH row. Blocking
        the signal temporarily makes Select All/None fast and avoids nested
        callbacks. The ``finally`` guarantees signals are restored.
        """
        was_blocked = self.list.blockSignals(True)
        try:
            for i in range(self.list.count()):
                self.list.item(i).setCheckState(
                    Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
        finally:
            self.list.blockSignals(was_blocked)
        self._refresh()

    def selected_ids(self):
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]

    def _refresh(self, *_):
        ids = set(self.selected_ids())
        selected = [t for t in self.tabs if t.id in ids]
        self.summary.setText(
            f'{len(selected)} tabs · {sum(t.pages for t in selected):,} pages · '
            f'{readable_bytes(sum(t.bytes for t in selected))} of referenced assets')
        self.confirm.setEnabled(bool(selected))
