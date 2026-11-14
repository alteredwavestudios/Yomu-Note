"""Non-destructive, page-accurate review for Smart Import 3.0.

The importer has staged originals in its temporary uncommitted batch, but
NOTHING is added to Project.pages, page_groups or Undo until this dialog is
accepted. All edits operate on tiny lists of section metadata (<=300 entries).
One on-demand thumbnail is shown; no PDF pages are rasterised in bulk.
"""
from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSlider,
    QSpinBox, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .import_structure import (fixed_range_sections, section_tree,
                               validate_sections, MAX_IMPORT_DEPTH)
from .importers import image_for_page
from .import_selection import (filter_staged_import, parse_page_ranges,
                               select_source_pages)
from .tasks import start_task

ROLE_SECTION = Qt.ItemDataRole.UserRole


class SmartImportReviewDialog(QDialog):
    """Review boundaries, remove/rename headings, or insert manual chapters."""

    def __init__(self, parent, project, batches, structures, *, destination_label,
                 arrangement, structure_mode='auto', page_interval=20,
                 max_subgroup_depth=2, selection_only=False):
        super().__init__(parent)
        self.setWindowTitle('Import — select pages and chapters' if selection_only
                            else 'Smart Import — review and select pages')
        self.resize(960, 650)
        self.setMinimumSize(680, 470)
        self._closed = False
        self.project = project
        self.batches = batches
        self.arrangement = arrangement
        self.selection_only = selection_only
        self._file_index = 0
        self._updating = False
        self._history_restore = False
        self._preview_generation = 0
        # Keep direct references to the CURRENT tree items. A checkbox click must
        # never clear/recreate its QTreeWidgetItem while Qt is dispatching the
        # item's change notification (a native use-after-free on some systems).
        self._tree_section_items = []
        self._analyses = structures
        self._original = []
        self._sections = []
        self._enabled = []  # one independent include flag for each outline heading
        self._all_pages = [True] * len(batches)
        self._range_strings = [''] * len(batches)
        self._frontmatter = [True] * len(batches)
        self._selected_at_accept = None
        for (_name, pages), analysis in zip(batches, structures):
            if structure_mode == 'ranges':
                entries = fixed_range_sections(len(pages), page_interval)
            elif structure_mode == 'none':
                entries = []
            else:
                entries = [section for section in analysis.get('sections', [])
                           if section['level'] <= max_subgroup_depth]
            verified = validate_sections(deepcopy(entries), len(pages))
            self._original.append(deepcopy(verified))
            self._sections.append(verified)
            self._enabled.append([True] * len(verified))
        self._past = []
        self._future = []

        layout = QVBoxLayout(self)
        heading = QLabel('Choose which pages to import. Everything is selected by default. '
                         'Uncheck chapters to omit them, or enter physical page ranges. '
                         'You can still adjust chapter titles and boundaries before importing.')
        heading.setWordWrap(True)
        layout.addWidget(heading)
        destination = QLabel(f'Destination: {destination_label}    ·    '
                             f'Arrangement: {"Separate file groups" if arrangement == "per_file" else "One combined group"}')
        destination.setWordWrap(True)
        layout.addWidget(destination)
        selector = QHBoxLayout()
        selector.addWidget(QLabel('Source file:'))
        self.source_select = QComboBox()
        for name, pages in batches:
            self.source_select.addItem(f'{name} ({len(pages)} pages)')
        selector.addWidget(self.source_select, 1)
        self.analysis_status = QLabel()
        self.analysis_status.setWordWrap(True)
        layout.addLayout(selector)
        layout.addWidget(self.analysis_status)
        page_filter = QHBoxLayout()
        self.all_pages_check = QCheckBox('All page numbers (default)')
        self.all_pages_check.setChecked(True)
        page_filter.addWidget(self.all_pages_check)
        self.page_range_edit = QLineEdit()
        self.page_range_edit.setPlaceholderText('e.g. 1-10, 25, 40-55')
        self.page_range_edit.setToolTip('Physical source-page numbers, inclusive; separate ranges with commas.')
        self.page_range_edit.setEnabled(False)
        page_filter.addWidget(self.page_range_edit, 1)
        layout.addLayout(page_filter)
        self.frontmatter_check = QCheckBox('Include pages before the first chapter (cover / front matter)')
        self.frontmatter_check.setChecked(True)
        layout.addWidget(self.frontmatter_check)
        self.chapter_hint = QLabel('Chapter checkboxes select their own pages; unchecking a chapter also unchecks its subsections. '
                                   'Page ranges and chapter choices are combined (intersection).')
        self.chapter_hint.setWordWrap(True)
        layout.addWidget(self.chapter_hint)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Include chapter / subsection', 'Source pages', 'Source'])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Only titles should be editable. The page range and provenance
        # columns are explanations, not writable model fields.
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setColumnWidth(0, 230)
        self.tree.setColumnWidth(1, 78)
        ll.addWidget(self.tree, 1)
        self.expand_review = QCheckBox('Expand all chapters in review')
        self.expand_review.setChecked(False)  # Start with a manageable outline.
        self.expand_review.toggled.connect(
            lambda expanded: self.tree.expandAll() if expanded else self.tree.collapseAll())
        ll.addWidget(self.expand_review)
        chapter_controls = QHBoxLayout()
        self.select_all_chapters = QPushButton('Select all chapters')
        self.select_no_chapters = QPushButton('Select none')
        chapter_controls.addWidget(self.select_all_chapters)
        chapter_controls.addWidget(self.select_no_chapters)
        ll.addLayout(chapter_controls)
        actions1 = QHBoxLayout()
        self.add_chapter = QPushButton('+ Chapter')
        self.add_sub = QPushButton('+ Subsection')
        self.remove = QPushButton('Merge / remove')
        for button in (self.add_chapter, self.add_sub, self.remove):
            actions1.addWidget(button)
        ll.addLayout(actions1)
        actions2 = QHBoxLayout()
        self.promote = QPushButton('Outdent')
        self.demote = QPushButton('Indent')
        self.undo_button = QPushButton('Undo')
        self.redo_button = QPushButton('Redo')
        self.reset = QPushButton('Reset detected')
        for button in (self.promote, self.demote, self.undo_button,
                       self.redo_button, self.reset):
            actions2.addWidget(button)
        ll.addLayout(actions2)
        splitter.addWidget(left)

        right = QWidget()
        rr = QVBoxLayout(right)
        rr.setContentsMargins(6, 0, 0, 0)
        rr.addWidget(QLabel('Page preview — actual physical source pages'))
        self.page_preview = QLabel('Select a page to preview')
        self.page_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_preview.setMinimumHeight(210)
        self.page_preview.setStyleSheet('QLabel { background: palette(base); border: 1px solid palette(mid); border-radius: 7px; }')
        rr.addWidget(self.page_preview, 1)
        self.page_position = QLabel()
        rr.addWidget(self.page_position)
        self.page_slider = QSlider(Qt.Orientation.Horizontal)
        self.page_slider.setMinimum(1)
        self.preview_page_spin = QSpinBox()
        self.preview_page_spin.setMinimum(1)
        self.preview_page_spin.setPrefix('Page ')
        page_nav = QHBoxLayout()
        page_nav.addWidget(self.page_slider, 1)
        page_nav.addWidget(self.preview_page_spin)
        rr.addLayout(page_nav)
        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setMaxLength(120)
        form.addRow('Chapter title:', self.title_edit)
        self.start_spin = QSpinBox()
        self.start_spin.setMinimum(1)
        form.addRow('Starts on PDF page:', self.start_spin)
        self.level_spin = QSpinBox()
        self.level_spin.setRange(1, MAX_IMPORT_DEPTH)
        form.addRow('Nesting level:', self.level_spin)
        rr.addLayout(form)
        boundary_actions = QHBoxLayout()
        self.use_preview_page = QPushButton('Set start to preview page')
        self.apply = QPushButton('Apply chapter changes')
        boundary_actions.addWidget(self.use_preview_page)
        boundary_actions.addWidget(self.apply)
        rr.addLayout(boundary_actions)
        note = QLabel('Moving a boundary changes the adjacent page ranges automatically. '
                      'Removing a heading keeps all its pages. '
                      'Printed page numbers may differ from PDF page numbers.')
        note.setWordWrap(True)
        rr.addWidget(note)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        self.coverage = QLabel('All pages will be imported exactly once.')
        layout.addWidget(self.coverage)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Import reviewed pages')
        layout.addWidget(buttons)
        buttons.accepted.connect(self._accept_checked)
        buttons.rejected.connect(self.reject)
        self.source_select.currentIndexChanged.connect(self._switch_file)
        self.tree.currentItemChanged.connect(self._choose_section)
        self.tree.itemChanged.connect(self._item_changed)
        self.all_pages_check.toggled.connect(self._range_mode_changed)
        self.page_range_edit.textChanged.connect(self._range_text_changed)
        self.frontmatter_check.toggled.connect(self._frontmatter_changed)
        self.select_all_chapters.clicked.connect(lambda: self._toggle_all_chapters(True))
        self.select_no_chapters.clicked.connect(lambda: self._toggle_all_chapters(False))
        self.tree.itemDoubleClicked.connect(
            lambda item, column: self.tree.editItem(item, 0) if column == 0 else None)
        self.page_slider.valueChanged.connect(self._page_moved)
        self.preview_page_spin.valueChanged.connect(self.page_slider.setValue)
        self.apply.clicked.connect(self._apply_fields)
        self.use_preview_page.clicked.connect(self._move_boundary_to_preview)
        self.add_chapter.clicked.connect(lambda: self._insert_heading(1))
        self.add_sub.clicked.connect(lambda: self._insert_heading(2))
        self.remove.clicked.connect(self._remove_heading)
        self.promote.clicked.connect(lambda: self._change_indent(-1))
        self.demote.clicked.connect(lambda: self._change_indent(1))
        self.undo_button.clicked.connect(self._undo)
        self.redo_button.clicked.connect(self._redo)
        self.reset.clicked.connect(self._reset)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self._render_page)
        self._switch_file(0)
        self._refresh_history()

    def sections_by_file(self):
        return deepcopy(self._sections)

    def selected_pages_by_file(self):
        """Source page numbers chosen when the user accepted this dialog."""
        if self._selected_at_accept is None:
            raise ValueError('Page choices are not confirmed yet.')
        return deepcopy(self._selected_at_accept)

    def _save_filter_controls(self):
        i = self._file_index
        self._all_pages[i] = self.all_pages_check.isChecked()
        self._range_strings[i] = self.page_range_edit.text()
        self._frontmatter[i] = self.frontmatter_check.isChecked()

    def _range_mode_changed(self, checked):
        if self._updating:
            return
        self.page_range_edit.setEnabled(not checked)
        self._save_filter_controls()
        self._refresh_selection_summary()
        self._page_moved(self.page_slider.value())

    def _range_text_changed(self, _value):
        if not self._updating:
            self._save_filter_controls()
            self._refresh_selection_summary()
            self._page_moved(self.page_slider.value())

    def _frontmatter_changed(self, _value):
        if not self._updating:
            self._save_filter_controls()
            self._refresh_selection_summary()
            self._page_moved(self.page_slider.value())

    def _choices_for_file(self, i):
        count = len(self.batches[i][1])
        page_range = (None if self._all_pages[i] else
                      parse_page_ranges(self._range_strings[i], count))
        return select_source_pages(count, self._sections[i],
                                   page_range=page_range,
                                   section_enabled=self._enabled[i],
                                   include_frontmatter=self._frontmatter[i])

    def _refresh_selection_summary(self):
        try:
            chosen = [self._choices_for_file(i) for i in range(len(self.batches))]
        except ValueError as exc:
            self.coverage.setText(f'Check page ranges: {exc}')
            return
        kept = sum(map(len, chosen))
        total = sum(len(pages) for _name, pages in self.batches)
        self.coverage.setText(f'Selected {kept:,} of {total:,} source pages. '
                              'Only selected pages will be imported, once each, in source order.')

    def _item_changed(self, item, column):
        """Apply checkbox edits WITHOUT destroying the item Qt is clicking.

        QTreeWidget.itemChanged is emitted synchronously while native Qt code
        still holds the item. Rebuilding/clearing the tree inside this callback
        can produce a hard Windows/macOS process crash, not a Python exception.
        """
        if self._updating or column != 0:
            return
        index = item.data(0, ROLE_SECTION)
        if index is None or not 0 <= index < len(self._sections[self._file_index]):
            return
        if item.text(0) != self._sections[self._file_index][index]['title']:
            self._title_changed(item, column)
            return
        checked_state = item.checkState(0)
        if checked_state == Qt.CheckState.PartiallyChecked:
            # Partial is a computed parent display state, not a user choice.
            return
        new_checked = checked_state == Qt.CheckState.Checked
        descendants = [index]
        for j in range(index + 1, len(self._sections[self._file_index])):
            if self._sections[self._file_index][j]['level'] <= self._sections[self._file_index][index]['level']:
                break
            descendants.append(j)
        flags = list(self._enabled[self._file_index])
        for j in descendants:
            flags[j] = new_checked
        if flags == self._enabled[self._file_index]:
            # A leaf could be clicked without changing the underlying selection
            # (e.g. a parent whose mixed state was already normalised).
            self._sync_chapter_checkboxes()
            return
        self._remember_history()
        self._enabled[self._file_index] = flags
        self._sync_chapter_checkboxes()
        self._refresh_history()
        self._refresh_selection_summary()
        self._update_page_status(self.page_slider.value())

    def _sync_chapter_checkboxes(self):
        """Repaint check/partial states in-place, preserving Qt item lifetime.

        Tree items are re-created ONLY by _rebuild for structural edits, never
        in response to a user checkbox toggle. Block itemChanged temporarily
        so updating a parent's partial state cannot recurse into this handler.
        """
        previous = self.tree.blockSignals(True)
        try:
            for index, item in enumerate(self._tree_section_items):
                desired = self._checkbox_state(index)
                if item.checkState(0) != desired:
                    item.setCheckState(0, desired)
        finally:
            self.tree.blockSignals(previous)

    def _toggle_all_chapters(self, checked):
        flags = [checked] * len(self._enabled[self._file_index])
        if flags != self._enabled[self._file_index]:
            self._remember_history()
            self._enabled[self._file_index] = flags
            self._sync_chapter_checkboxes()
            self._refresh_history()
            self._refresh_selection_summary()
            self._update_page_status(self.page_slider.value())

    def _remember_history(self):
        i = self._file_index
        self._past.append((i, deepcopy(self._sections[i]), list(self._enabled[i])))
        self._future.clear()

    def _checkbox_state(self, index):
        enabled = self._enabled[self._file_index]
        sections = self._sections[self._file_index]
        descendants = [enabled[index]]
        for j in range(index + 1, len(sections)):
            if sections[j]['level'] <= sections[index]['level']:
                break
            descendants.append(enabled[j])
        if all(descendants):
            return Qt.CheckState.Checked
        if not any(descendants):
            return Qt.CheckState.Unchecked
        return Qt.CheckState.PartiallyChecked

    def _selected_index(self):
        item = self.tree.currentItem()
        return item.data(0, ROLE_SECTION) if item is not None else None

    def _switch_file(self, file_index):
        if not 0 <= file_index < len(self.batches):
            return
        if file_index != self._file_index and not self._history_restore:
            # A user switching to the next PDF shouldn't silently lose a
            # boundary/name typed into the properties editor.
            if not self._apply_fields():
                self.source_select.blockSignals(True)
                self.source_select.setCurrentIndex(self._file_index)
                self.source_select.blockSignals(False)
                return
        if not self._history_restore:
            self._save_filter_controls()
        self._file_index = file_index
        self._updating = True
        try:
            self.all_pages_check.setChecked(self._all_pages[file_index])
            self.page_range_edit.setText(self._range_strings[file_index])
            self.page_range_edit.setEnabled(not self._all_pages[file_index])
            self.frontmatter_check.setChecked(self._frontmatter[file_index])
            headings = self._sections[file_index]
            self.frontmatter_check.setVisible(bool(headings and headings[0]['start'] > 1))
        finally:
            self._updating = False
        name, pages = self.batches[file_index]
        details = self._analyses[file_index]
        self.page_slider.setMaximum(len(pages))
        self.preview_page_spin.setMaximum(len(pages))
        self.page_slider.setValue(1)
        self.start_spin.setMaximum(len(pages))
        warnings = '; '.join(details.get('warnings', [])[:3])
        self.analysis_status.setText(
            f"{len(self._sections[file_index])} proposed sections · "
            f"Source: {details.get('source', 'Manual / fixed range')}. "
            + (warnings + ' ' if warnings else '')
            + ('No reliable outline? Create your own using + Chapter.'
               if not self._sections[file_index] else
               'Every page is retained even if you merge/remove headings.'))
        self._rebuild()
        self._page_moved(self.page_slider.value())

    def _end_page(self, sections, row, total):
        for next_row in sections[row+1:]:
            if next_row['level'] <= sections[row]['level']:
                return next_row['start'] - 1
        return total

    def _rebuild(self, select_row=None):
        sections = self._sections[self._file_index]
        self._updating = True
        try:
            # Forget old wrappers BEFORE Qt deletes their native counterparts.
            self._tree_section_items = []
            self.tree.clear()
            parents = []
            for index, section in enumerate(sections):
                item = QTreeWidgetItem([section['title'],
                    f"{section['start']}–{self._end_page(sections, index, len(self.batches[self._file_index][1]))}",
                    section.get('origin', '')])
                item.setData(0, ROLE_SECTION, index)
                self._tree_section_items.append(item)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable |
                              Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, self._checkbox_state(index))
                while len(parents) >= section['level']:
                    parents.pop()
                if parents:
                    parents[-1].addChild(item)
                else:
                    self.tree.addTopLevelItem(item)
                parents.append(item)
            if self.expand_review.isChecked():
                self.tree.expandAll()
            else:
                self.tree.collapseAll()
            if sections:
                chosen = 0 if select_row is None else min(max(0, select_row), len(sections)-1)
                it = self._item_for_index(chosen)
                if it is not None:
                    self.tree.setCurrentItem(it)
            else:
                self.title_edit.clear()
                self.start_spin.setValue(1)
                self.level_spin.setValue(1)
        finally:
            self._updating = False
        self._choose_section(self.tree.currentItem(), None)
        self._refresh_history()
        self._refresh_selection_summary()

    def _item_for_index(self, target):
        def walk(item):
            if item.data(0, ROLE_SECTION) == target:
                return item
            for i in range(item.childCount()):
                result = walk(item.child(i))
                if result is not None:
                    return result
            return None
        for i in range(self.tree.topLevelItemCount()):
            result = walk(self.tree.topLevelItem(i))
            if result is not None:
                return result
        return None

    def _choose_section(self, current, previous):
        if self._updating:
            return
        index = self._selected_index()
        selected = self._sections[self._file_index]
        enabled = index is not None and index < len(selected)
        for control in (self.title_edit, self.start_spin, self.level_spin,
                        self.apply, self.use_preview_page, self.remove, self.promote, self.demote):
            control.setEnabled(enabled)
        self.add_sub.setEnabled(enabled)
        if enabled:
            heading = selected[index]
            self.title_edit.setText(heading['title'])
            self.start_spin.setValue(heading['start'])
            self.level_spin.setValue(heading['level'])
            self.page_slider.setValue(heading['start'])

    def _update_page_status(self, number):
        """A chapter toggle updates the INCLUDED label, not the PDF preview."""
        try:
            included = number in self._choices_for_file(self._file_index)
            status = 'INCLUDED' if included else 'EXCLUDED'
        except ValueError:
            status = 'Check page range'
        self.page_position.setText(
            f'Physical source page {number} / {len(self.batches[self._file_index][1])} · {status}')

    def _page_moved(self, number):
        self.preview_page_spin.setValue(number)
        self._update_page_status(number)
        self.page_preview.setText('Loading page preview…')
        self._preview_generation += 1
        self._preview_timer.start()

    def _render_page(self):
        file_index = self._file_index
        page_number = self.page_slider.value()
        generation = self._preview_generation
        page = self.batches[file_index][1][page_number - 1]
        def worker():
            if self._closed:
                return None
            return str(image_for_page(self.project, page, thumbnail=True, thumb_width=240))
        def complete(path, error):
            if (self._closed or generation != self._preview_generation or
                    file_index != self._file_index):
                return
            if error or not path:
                self.page_preview.setText('Preview unavailable. Page will still be imported.')
                return
            decoded = QImageReader(path).read()
            if decoded.isNull():
                self.page_preview.setText('Preview unavailable.')
                return
            pix = QPixmap.fromImage(decoded).scaled(
                340, 370, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self.page_preview.setPixmap(pix)
        start_task(self, worker, complete, priority=-1)

    def _commit(self, new_sections, select_row=None, new_enabled=None, *, rebuild=True):
        try:
            approved = validate_sections(new_sections, len(self.batches[self._file_index][1]))
            section_tree([p['id'] for p in self.batches[self._file_index][1]], approved)
        except ValueError as exc:
            QMessageBox.warning(self, 'Invalid chapter structure', str(exc))
            return False
        if new_enabled is None:
            new_enabled = list(self._enabled[self._file_index])
        if len(new_enabled) != len(approved) or any(type(x) is not bool for x in new_enabled):
            raise ValueError('Chapter checkbox choices do not match the edited outline.')
        if approved == self._sections[self._file_index] and new_enabled == self._enabled[self._file_index]:
            return True
        self._remember_history()
        self._sections[self._file_index] = approved
        self._enabled[self._file_index] = list(new_enabled)
        if rebuild:
            self._rebuild(select_row)
        else:
            # Only used for a title edit: no change to the outline's shape.
            self._refresh_history()
            self._refresh_selection_summary()
        return True

    def _move_boundary_to_preview(self):
        if self._selected_index() is not None:
            self.start_spin.setValue(self.page_slider.value())
            self._apply_fields()

    def _apply_fields(self):
        i = self._selected_index()
        if i is None:
            return True
        changes = deepcopy(self._sections[self._file_index])
        changes[i].update(title=self.title_edit.text().strip(),
                          start=self.start_spin.value(), level=self.level_spin.value(),
                          origin='Edited in review')
        return self._commit(changes, i)

    def _title_changed(self, item, column):
        if self._updating or column != 0:
            return
        index = item.data(0, ROLE_SECTION)
        if index is None:
            return
        changes = deepcopy(self._sections[self._file_index])
        changes[index]['title'] = item.text(0)
        changes[index]['origin'] = 'Edited in review'
        # This also runs inside itemChanged. A title edit must not rebuild the
        # tree until Qt has returned from the native edit notification.
        if self._commit(changes, index, rebuild=False):
            previous = self.tree.blockSignals(True)
            try:
                item.setText(2, 'Edited in review')
            finally:
                self.tree.blockSignals(previous)
            self.title_edit.setText(changes[index]['title'])
        else:
            previous = self.tree.blockSignals(True)
            try:
                item.setText(0, self._sections[self._file_index][index]['title'])
            finally:
                self.tree.blockSignals(previous)

    def _insert_heading(self, desired_level):
        changes = deepcopy(self._sections[self._file_index])
        start = self.page_slider.value()
        if desired_level == 2:
            chosen = self._selected_index()
            if chosen is None:
                return
            desired_level = min(MAX_IMPORT_DEPTH, changes[chosen]['level'] + 1)
            # A subsection can only be inserted within its selected parent's
            # range, never into a different chapter.
            end = self._end_page(changes, chosen, len(self.batches[self._file_index][1]))
            if not changes[chosen]['start'] <= start <= end:
                QMessageBox.information(self, 'Page outside chapter',
                    'Select a page inside the chosen parent chapter first.')
                return
        insert_at = next((i for i,s in enumerate(changes)
                          if s['start'] > start), len(changes))
        new = {'title': 'New subsection' if desired_level > 1 else 'New chapter',
               'start': start, 'level': desired_level, 'origin': 'Manual'}
        changes.insert(insert_at, new)
        flags = list(self._enabled[self._file_index])
        flags.insert(insert_at, True)
        self._commit(changes, insert_at, flags)

    def _remove_heading(self):
        i = self._selected_index()
        if i is None:
            return
        changes = deepcopy(self._sections[self._file_index])
        level = changes[i]['level']
        changes.pop(i)
        flags = list(self._enabled[self._file_index])
        flags.pop(i)
        # Removing a parent promotes its children instead of erasing their
        # pages or section names. Subsequent siblings are unaffected.
        j = i
        while j < len(changes) and changes[j]['level'] > level:
            changes[j]['level'] -= 1
            j += 1
        self._commit(changes, max(0, i - 1), flags)

    def _change_indent(self, delta):
        i = self._selected_index()
        if i is None:
            return
        changes = deepcopy(self._sections[self._file_index])
        level = changes[i]['level']
        j = i + 1
        while j < len(changes) and changes[j]['level'] > level:
            j += 1
        for k in range(i, j):
            changes[k]['level'] += delta
        self._commit(changes, i)

    def _reset(self):
        defaults = deepcopy(self._original[self._file_index])
        flags = [True] * len(defaults)
        if (self._sections[self._file_index] == defaults and
                self._enabled[self._file_index] == flags):
            self._rebuild(0)  # also reset un-applied properties-field edits
        else:
            self._commit(defaults, 0, flags)

    def _refresh_history(self):
        self.undo_button.setEnabled(bool(self._past))
        self.redo_button.setEnabled(bool(self._future))

    def _undo(self):
        if not self._past:
            return
        i, snapshot, flags = self._past.pop()
        self._future.append((i, deepcopy(self._sections[i]), list(self._enabled[i])))
        self._sections[i] = snapshot
        self._enabled[i] = flags
        self._history_restore = True
        try:
            self.source_select.setCurrentIndex(i)
        finally:
            self._history_restore = False
        self._rebuild()

    def _redo(self):
        if not self._future:
            return
        i, snapshot, flags = self._future.pop()
        self._past.append((i, deepcopy(self._sections[i]), list(self._enabled[i])))
        self._sections[i] = snapshot
        self._enabled[i] = flags
        self._history_restore = True
        try:
            self.source_select.setCurrentIndex(i)
        finally:
            self._history_restore = False
        self._rebuild()

    def _accept_checked(self):
        # Pressing Import should never discard edits still in the properties
        # panel because the user forgot to click Apply first.
        if not self._apply_fields():
            return
        self._save_filter_controls()
        try:
            chosen = [self._choices_for_file(i) for i in range(len(self.batches))]
            retained, remapped, _omitted = filter_staged_import(
                self.batches, self._sections, chosen)
            for (_name, pages), sections in zip(retained, remapped):
                section_tree([page['id'] for page in pages], sections)
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot import', str(exc))
            return
        self._selected_at_accept = chosen
        self.accept()

    def done(self, result):
        self._closed = True
        self._preview_timer.stop()
        super().done(result)
