"""Native tables for the rich-text notes editor.

BEGINNER GUIDE
==============
A *table* is a grid of cells, like a small spreadsheet.

We do not make separate text widgets for its cells.
Qt already knows how to keep real tables inside QTextDocument.
That is important: the table then saves with the note's HTML,
uses the same text formatting, and participates in Undo.

An invisible table is useful for arranging text in columns.
When the caret is inside one, a temporary guide is painted
on the screen. That guide is NOT saved into the document.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QPainter, QPen, QTextBlockFormat, QTextCursor,
    QTextLength, QTextTableFormat, QTextTableCellFormat,
)
from shiboken6 import isValid
from .table_grid import (
    proportional_column_edges, grid_segments, would_cut_merged_cell,
    resize_adjacent_percentages, closest_table_edge,
)

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QMenu, QMessageBox, QSpinBox, QDoubleSpinBox,
    QVBoxLayout, QLabel, QDialogButtonBox,
)


# Each limit keeps the interface responsive even if the user
# accidentally types a very large number into the dialog.
_MAX_ROWS = 100
_MAX_COLUMNS = 20
_MAX_CELLS = 1000
_DEFAULT_PADDING = 4.0
_MAX_ROW_EXTRA = 240.0

# Qt measures table-frame margins in logical display pixels.
# Use a small, consistent step rather than changing cell styles.
_TABLE_INDENT_STEP = 18.0
_MAX_TABLE_INDENT = 216.0


# A Python wrapper can outlive the C++ object managed by Qt.
# When the document rebuilds a table during Undo, it may destroy
# the old C++ table even though Python still has its wrapper.
# Never keep those wrappers in long-lived mouse-hover state.

def _live_table(table):
    """Return True only while Qt still owns this QTextTable."""
    return table is not None and isValid(table)


def _table_position(table):
    """Store the first cell's position, not its C++ table object."""
    if not _live_table(table):
        return None
    try:
        cell = table.cellAt(0, 0)
        return (cell.firstCursorPosition().position()
                if cell.isValid() else None)
    except RuntimeError:
        return None


def _table_at_position(editor, position):
    """Look up a FRESH table from the current document."""
    if position is None:
        return None
    document = editor.document()
    if not 0 <= position < document.characterCount():
        return None
    try:
        cursor = QTextCursor(document)
        cursor.setPosition(position)
        table = cursor.currentTable()
        return table if _live_table(table) else None
    except (RuntimeError, ValueError):
        return None


def _hover_table(editor):
    """Hover stores a character position, never a QTextTable wrapper."""
    return _table_at_position(
        editor, getattr(editor, '_table_hover_position', None))


def _drag_table(editor, drag):
    """Cancel a drag if editing has replaced its original table."""
    if not drag or editor._table_edit_serial != drag['edit_serial']:
        return None
    table = _table_at_position(editor, drag['table_position'])
    if (_table_position(table) != drag['table_position'] or
            not _live_table(table)):
        return None
    return table


class InsertTableDialog(QDialog):
    """Ask for the shape and borders of a new table."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Insert table')
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            'Create a text layout with editable rows and columns.'))
        form = QFormLayout()
        self.rows = QSpinBox(self)
        self.rows.setRange(1, _MAX_ROWS)
        self.rows.setValue(3)
        self.columns = QSpinBox(self)
        self.columns.setRange(1, _MAX_COLUMNS)
        self.columns.setValue(2)
        self.borders = QCheckBox('Show permanent borders', self)
        self.borders.setChecked(False)
        self.borders.setToolTip(
            'Unchecked tables still show faint guides while editing.\n'
            'The guides are not saved or exported.')
        form.addRow('Rows', self.rows)
        form.addRow('Columns', self.columns)
        form.addRow(self.borders)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.rows.valueChanged.connect(self._limit_cells)
        self.columns.valueChanged.connect(self._limit_cells)

    def _limit_cells(self, _value):
        # A table with thousands of cells can freeze a text layout.
        # Limit the product, not just the individual dimensions.
        self.rows.setMaximum(min(_MAX_ROWS,
                                 max(1, _MAX_CELLS // self.columns.value())))
        self.columns.setMaximum(min(_MAX_COLUMNS,
                                    max(1, _MAX_CELLS // self.rows.value())))


class TableSizeDialog(QDialog):
    """Precise sizes for the current column and row.

    Qt supports native percentage column widths. It does not
    offer a native fixed minimum height for ONE table row.
    We use extra bottom padding in that row instead, so the
    cell still grows automatically when text needs more room.
    """

    def __init__(self, percentage, row_extra, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Table size and spacing')
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            'Adjust the selected column and row. Changes are undoable.'))
        form = QFormLayout()
        self.column = QDoubleSpinBox(self)
        self.column.setRange(0.1, 100.0)
        self.column.setDecimals(1)
        self.column.setSingleStep(2.5)
        self.column.setSuffix(' %')
        self.column.setValue(float(percentage))
        self.column.setToolTip(
            'Relative width of this column.\n'
            'The adjacent column makes up the difference.')
        self.row = QDoubleSpinBox(self)
        self.row.setRange(0.0, _MAX_ROW_EXTRA)
        self.row.setDecimals(1)
        self.row.setSingleStep(4.0)
        self.row.setSuffix(' px')
        self.row.setValue(float(row_extra))
        self.row.setToolTip(
            'Extra vertical space after the text in this row.\n'
            'Zero means automatic row height. Text can always grow.')
        form.addRow('Column width', self.column)
        form.addRow('Extra row space', self.row)
        layout.addLayout(form)
        layout.addWidget(QLabel(
            'Row height is content-based; extra space never clips text.'))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class TableTools:
    """Commands called by the toolbar and the right-click menu.

    `notes` is our NotesEditor widget. Its `editor` field is the
    QTextEdit containing all the actual paragraphs and tables.
    We obtain `notes.editor` only when an action is triggered,
    because the toolbar is built before the text widget exists.
    """

    def __init__(self, notes):
        self.notes = notes

    @property
    def editor(self):
        return self.notes.editor

    def current(self):
        return self.editor.textCursor().currentTable()

    @staticmethod
    def new_format(columns: int, borders: bool = False):
        """Make a layout table that fits the available text width."""
        fmt = QTextTableFormat()
        fmt.setBorder(1.0 if borders else 0.0)
        # A little padding keeps the editing guides from touching
        # the letters, even when the saved border is invisible.
        fmt.setCellPadding(_DEFAULT_PADDING)
        fmt.setCellSpacing(0.0)
        fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100.0))
        fmt.setColumnWidthConstraints([
            QTextLength(QTextLength.Type.PercentageLength, 100.0 / columns)
            for _ in range(columns)
        ])
        if hasattr(fmt, 'setBorderCollapse'):
            fmt.setBorderCollapse(True)
        return fmt

    def build_menu(self, parent=None, *, include_insert=True):
        """Offer the same commands in toolbar and right-click menus.

        The shortcuts are defined only once in platform_shortcuts.
        Context menus display them, but do not register duplicate
        keyboard handlers (which could run a command twice).
        """
        from .platform_shortcuts import docs_shortcut
        # Give this submenu an explicit title. Qt otherwise shows
        # an empty menu row with an arrow in the right-click menu.
        menu = QMenu('Edit Table', parent or self.notes)
        if include_insert:
            menu.addAction(
                f'Insert table…  ·  {docs_shortcut("insert_table")}',
                self.insert_table)
            menu.addSeparator()
        actions = {}
        for name, title, callback, hint in (
            ('row_before', 'Add row above', self.add_row_above,
             'table_row_before'),
            ('row', 'Add row below', self.add_row_below,
             'table_row_after'),
            ('column_before', 'Add column left', self.add_column_left,
             'table_column_before'),
            ('column', 'Add column right', self.add_column_right,
             'table_column_after'),
        ):
            actions[name] = menu.addAction(
                f'{title}  ·  {docs_shortcut(hint)}', callback)
        menu.addSeparator()
        actions['select'] = menu.addAction(
            'Select entire table', self.select_table)
        actions['remove_row'] = menu.addAction(
            f'Delete current row  ·  '
            f'{docs_shortcut("table_delete_row")}', self.remove_row)
        actions['remove_column'] = menu.addAction(
            f'Delete current column  ·  '
            f'{docs_shortcut("table_delete_column")}', self.remove_column)
        # Deleting a table removes its cell text too, as one native
        # Undo step. No hidden copy is included in saved notes HTML.
        actions['delete_table'] = menu.addAction(
            'Delete entire table', self.delete_table)
        menu.addSeparator()
        # These margins belong to the table frame, not to any cell.
        # The user can move the WHOLE layout without altering its text.
        actions['indent_table'] = menu.addAction(
            'Indent whole table right (18 px)', self.indent_table_right)
        actions['outdent_table'] = menu.addAction(
            'Outdent whole table left (18 px)', self.outdent_table_left)
        menu.addSeparator()
        actions['merge'] = menu.addAction(
            'Merge selected cells', self.merge_selected_cells)
        actions['split'] = menu.addAction(
            'Split merged cell', self.split_cell)
        actions['header'] = menu.addAction(
            'First row is a header', self.toggle_header)
        actions['header'].setCheckable(True)
        actions['borders'] = menu.addAction(
            'Show permanent borders', self.toggle_borders)
        actions['borders'].setCheckable(True)
        menu.addSeparator()
        padding = menu.addMenu('Cell padding')
        for pixels, label in ((0.0, 'None (0 px)'),
                              (4.0, 'Compact (4 px)'),
                              (8.0, 'Comfortable (8 px)')):
            padding.addAction(
                label, lambda checked=False, value=pixels:
                self.set_cell_padding(value))
        actions['properties'] = menu.addAction(
            'Table size and spacing…', self.table_properties)
        menu.addAction('Equal-width columns', self.equalise_columns)
        menu.addAction(
            'Make old table columns resizable (equal widths)',
            self.initialise_percentage_widths)
        menu.aboutToShow.connect(lambda: self._refresh_menu(actions))
        return menu

    def handle_pointer(self, phase, position):
        """Preview a drag, then commit ONE real edit at mouse release.

        Qt tables are owned by QTextDocument. We remember only
        integer document positions and measurements during a drag.
        Holding a QTextTable wrapper would make it unsafe after
        text alignment, Undo, or a document re-layout.
        """
        editor = self.editor
        drag = editor._table_drag

        if phase == 'cancel':
            editor.clear_table_interaction()
            return True

        if phase == 'release' and drag is not None:
            # A mouse release always ends a gesture. Do not rely on
            # Qt's focus or layout callbacks to clear the visual line.
            table = _drag_table(editor, drag)
            editor.clear_table_interaction()
            if table is None:
                return True
            if drag['kind'] == 'column':
                self.set_column_widths(table, drag['preview'])
            elif abs(drag['preview'] - drag['original']) > 0.1:
                self.set_row_extra_space(
                    table, drag['index'] - 1, drag['preview'])
            return True

        if phase == 'move' and drag is not None:
            if _drag_table(editor, drag) is None:
                editor.clear_table_interaction()
                return True
            movement = (position.x() - drag['start'].x()
                        if drag['kind'] == 'column'
                        else position.y() - drag['start'].y())
            if drag['kind'] == 'column':
                width = max(1.0, drag['frame_width'])
                minimum = min(8.0, max(2.0, 24.0 * 100.0 / width))
                new_values = resize_adjacent_percentages(
                    drag['original'], drag['index'],
                    movement * sum(drag['original']) / width,
                    minimum)
                if new_values is not None:
                    drag['preview'] = new_values
            else:
                drag['delta'] = movement
                drag['preview'] = max(
                    0.0, min(_MAX_ROW_EXTRA,
                             drag['original'] + movement))
            editor.viewport().update()
            return True

        hit = table_interaction_hit(editor, position)
        if phase == 'press':
            if hit is None:
                return False
            kind, table, index, (frame, xs, ys) = hit
            if kind == 'select':
                self.select_table(table)
                return True
            widths = self._percentage_widths(table)
            if kind == 'column' and widths is None:
                return False
            start_position = _table_position(table)
            if start_position is None:
                return False
            # Remember only plain values: Qt may replace this table
            # object during Undo or when formatting a cell.
            editor._table_hover_position = start_position
            editor._table_drag = {
                'kind': kind, 'table_position': start_position,
                'edit_serial': editor._table_edit_serial,
                'index': index, 'start': QPointF(position),
                'frame_width': frame.width(),
                'original': (list(widths) if kind == 'column'
                             else self.row_extra_space(table, index - 1)),
                'preview': (list(widths) if kind == 'column'
                            else self.row_extra_space(table, index - 1)),
                'delta': 0.0,
            }
            # Qt implicitly tracks an ordinary left-button press.
            # Never call grabMouse() on the viewport: if a release
            # handler is replaced or missed, that can freeze Windows.
            # LinkTextEdit has a non-blocking watchdog as a fallback.
            editor.viewport().update()
            return True

        if phase == 'move':
            hovered = editor.cursorForPosition(
                position.toPoint()).currentTable()
            if _live_table(hovered):
                editor._table_hover_position = _table_position(hovered)
            elif editor._table_hover_position is not None:
                geometry = table_guide_geometry(editor, _hover_table(editor))
                if (geometry is None or not geometry[0].adjusted(
                        -15, -15, 8, 8).contains(position)):
                    editor._table_hover_position = None
            if hit is not None:
                kind = hit[0]
                shape = (Qt.CursorShape.PointingHandCursor
                         if kind == 'select' else
                         Qt.CursorShape.SplitHCursor
                         if kind == 'column' else
                         Qt.CursorShape.SplitVCursor)
                editor.viewport().setCursor(shape)
                editor.viewport().setToolTip(
                    ('Select table' if kind == 'select' else
                     'Drag to resize column · one Undo step'
                     if kind == 'column' else
                     'Drag for extra row space · one Undo step') +
                    '\n' + getattr(editor, 'table_hover_help', ''))
                editor.viewport().update()
                return True
            editor.viewport().unsetCursor()
            editor.viewport().update()
        return False

    @staticmethod
    def _owners(table):
        """Map every grid square to the REAL Qt cell that owns it.

        A merged cell occupies more than one square, but it has
        only one starting position in the document. This map
        helps us avoid cutting through it when deleting cells.
        """
        return [
            [table.cellAt(row, col).firstCursorPosition().position()
             for col in range(table.columns())]
            for row in range(table.rows())
        ]

    def _safe_to_delete(self, table, axis, index):
        """Refuse partial removal of merged cells.

        Qt can shift the remaining cells during deletion.
        We protect the user's data by requiring a split first
        whenever a merge spans the row/column being removed.
        """
        return not would_cut_merged_cell(
            self._owners(table), axis, index)

    @staticmethod
    def _percentage_widths(table):
        """Read actual Qt column proportions, if all are percentages.

        A custom-width table should not reset to equal widths
        when you simply add or delete a column.
        """
        values = table.format().columnWidthConstraints()
        if len(values) != table.columns():
            return None
        if any(value.type() != QTextLength.Type.PercentageLength
               or value.rawValue() <= 0 for value in values):
            return None
        return [value.rawValue() for value in values]

    @staticmethod
    def _apply_percentage_widths(table, values):
        """Save the new widths as part of the SAME Undo transaction."""
        total = sum(values)
        if total <= 0:
            return
        fmt = table.format()
        fmt.setColumnWidthConstraints([
            QTextLength(QTextLength.Type.PercentageLength,
                        100.0 * width / total)
            for width in values
        ])
        table.setFormat(fmt)

    def _safe_to_insert(self, table, axis, boundary):
        """Never insert through a merged cell belonging to another row.

        Qt may automatically extend merges during insertion.
        That could surprise someone who has carefully arranged
        neighbouring cells, so we require a split first instead.
        """
        owners = self._owners(table)
        if axis == 'row':
            if boundary <= 0 or boundary >= table.rows():
                return True
            return all(owners[boundary-1][col] != owners[boundary][col]
                       for col in range(table.columns()))
        if axis == 'column':
            if boundary <= 0 or boundary >= table.columns():
                return True
            return all(owners[row][boundary-1] != owners[row][boundary]
                       for row in range(table.rows()))
        return False

    def _explain_merged_insert(self):
        QMessageBox.information(
            self.notes, 'Split merged cells first',
            'That insertion point crosses a merged cell.\n\n'
            'Split it first so the existing cells remain intact.')

    def _explain_merged_delete(self):
        QMessageBox.information(
            self.notes,
            'Split merged cells first',
            'This row or column crosses a merged cell.\n\n'
            'Split the merged cell before deleting, so its '
            'neighbouring text cannot be rearranged unexpectedly.',
        )

    def _refresh_menu(self, actions):
        # Disable cell commands when the caret is not in a table.
        table = self.current()
        for action in actions.values():
            action.setEnabled(_live_table(table))
        if not _live_table(table):
            return
        fmt = table.format()
        actions['borders'].setChecked(fmt.border() > 0.0)
        actions['header'].setChecked(fmt.headerRowCount() > 0)
        cell = table.cellAt(self.editor.textCursor())
        if cell.isValid():
            actions['split'].setEnabled(
                cell.rowSpan() > 1 or cell.columnSpan() > 1)
        # Disable deletion that would slice through a merged cell.
        row_ok = (cell.isValid() and table.rows() > 1 and
                  self._safe_to_delete(table, 'row', cell.row()))
        column_ok = (cell.isValid() and table.columns() > 1 and
                     self._safe_to_delete(table, 'column', cell.column()))
        actions['remove_row'].setEnabled(row_ok)
        actions['remove_column'].setEnabled(column_ok)
        actions['merge'].setEnabled(self._selected_cells() is not None)
        actions['properties'].setEnabled(
            cell.isValid() and self._percentage_widths(table) is not None)
        table_margin = max(0.0, float(fmt.leftMargin()))
        actions['indent_table'].setEnabled(
            table_margin < _MAX_TABLE_INDENT - 0.01)
        actions['outdent_table'].setEnabled(table_margin > 0.01)

    def _perform(self, callback, *, keep_cursor=True):
        """Group a table operation into one native Undo step."""
        editor = self.editor

        def perform():
            writer = QTextCursor(editor.textCursor())
            writer.beginEditBlock()
            try:
                callback()
            finally:
                writer.endEditBlock()

        # Table operations can change the document's line wrapping.
        # Preserve the reading line but leave the new caret in its cell.
        editor.preserve_view_state(perform, restore_cursor=keep_cursor)
        editor.setFocus()
        editor.viewport().update()

    def _clear_cell_spacing(self, table, cells=None):
        """Avoid an 8 pt paragraph gap inside newly created cells.

        Qt gives each cell one ordinary paragraph to begin with.
        The document's paragraph spacing rules must not turn each
        table row into a widely spaced block of white space.
        """
        document = self.editor.document()
        cursor = QTextCursor(document)
        # Only modify NEW cells. Reformatting all existing cells
        # would erase a user's intentional paragraph spacing.
        if cells is None:
            cells = ((r, c) for r in range(table.rows())
                     for c in range(table.columns()))
        for row, col in cells:
            cell = table.cellAt(row, col)
            if not cell.isValid():
                continue
            block = cell.firstCursorPosition().block()
            fmt = block.blockFormat()
            if (fmt.topMargin() or fmt.bottomMargin() or
                    fmt.leftMargin() or fmt.textIndent()):
                fmt.setTopMargin(0.0)
                fmt.setBottomMargin(0.0)
                fmt.setLeftMargin(0.0)
                fmt.setTextIndent(0.0)
                cursor.setPosition(block.position())
                cursor.setBlockFormat(fmt)

    def insert_table(self):
        """Insert a real QTextTable, not HTML text pretending to be a grid."""
        dialog = InsertTableDialog(self.notes)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        rows, columns = dialog.rows.value(), dialog.columns.value()
        fmt = self.new_format(columns, dialog.borders.isChecked())

        def apply():
            cursor = QTextCursor(self.editor.textCursor())
            table = cursor.insertTable(rows, columns, fmt)
            self._clear_cell_spacing(table)
            self.editor.setTextCursor(
                table.cellAt(0, 0).firstCursorPosition())

        self._perform(apply, keep_cursor=False)

    def _insert_row(self, before):
        """Insert one row, leaving old content and formatting alone."""
        table = self.current()
        if table is None or table.rows() >= _MAX_ROWS:
            return
        cell = table.cellAt(self.editor.textCursor())
        if not cell.isValid():
            return
        target = cell.row() if before else cell.row() + cell.rowSpan()
        if not self._safe_to_insert(table, 'row', target):
            self._explain_merged_insert()
            return
        chosen_column = cell.column()

        def apply():
            table.insertRows(target, 1)
            self._clear_cell_spacing(
                table, ((target, col) for col in range(table.columns())))
            self.editor.setTextCursor(
                table.cellAt(target, chosen_column).firstCursorPosition())

        self._perform(apply, keep_cursor=False)

    def add_row_above(self):
        self._insert_row(True)

    def add_row_below(self):
        self._insert_row(False)

    def _insert_column(self, before):
        """Split the adjacent column's width, never equalise all of them."""
        table = self.current()
        if table is None or table.columns() >= _MAX_COLUMNS:
            return
        cell = table.cellAt(self.editor.textCursor())
        if not cell.isValid():
            return
        target = cell.column() if before else cell.column() + cell.columnSpan()
        if not self._safe_to_insert(table, 'column', target):
            self._explain_merged_insert()
            return
        chosen_row = cell.row()
        widths = self._percentage_widths(table)

        def apply():
            table.insertColumns(target, 1)
            if widths is not None:
                original = list(widths)
                neighbour = target if before else target - 1
                half = original[neighbour] / 2.0
                original[neighbour] = half
                original.insert(target, half)
                self._apply_percentage_widths(table, original)
            self._clear_cell_spacing(
                table, ((row, target) for row in range(table.rows())))
            self.editor.setTextCursor(
                table.cellAt(chosen_row, target).firstCursorPosition())

        self._perform(apply, keep_cursor=False)

    def add_column_left(self):
        self._insert_column(True)

    def add_column_right(self):
        self._insert_column(False)

    def select_table(self, table=None):
        """Select its real cells, not a picture of a rectangle.

        The QTextCursor selection is part of Qt's document model.
        A user can copy the selection, or format its text normally.
        This does not create an Undo entry because it edits no text.
        """
        table = table if table is not None else self.current()
        if table is None:
            return
        first = table.cellAt(0, 0).firstCursorPosition()
        last = table.cellAt(
            table.rows() - 1, table.columns() - 1).lastCursorPosition()
        cursor = QTextCursor(first)
        cursor.setPosition(last.position(), QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        # Mark this *explicit* corner-handle selection. Qt may
        # report cell selections in a different order from ordinary
        # text selections. We don't guess from highlighted text.
        self.editor._table_selected_range = (
            _table_position(table),
            cursor.selectionStart(), cursor.selectionEnd())
        self.editor.setFocus()
        self.editor.viewport().update()

    @staticmethod
    def row_extra_space(table, row):
        """Return extra row bottom padding in Qt layout pixels."""
        if not 0 <= row < table.rows():
            return 0.0
        cell = table.cellAt(row, 0)
        if not cell.isValid():
            return 0.0
        fmt = QTextTableCellFormat(cell.format())
        return max(0.0, fmt.bottomPadding())

    @staticmethod
    def _write_row_extra_space(table, row, points):
        """Set cell padding directly, inside an existing Undo group."""
        seen = set()
        for col in range(table.columns()):
            cell = table.cellAt(row, col)
            if not cell.isValid() or cell.row() != row:
                continue
            owner = cell.firstCursorPosition().position()
            if owner in seen:
                continue
            seen.add(owner)
            fmt = QTextTableCellFormat(cell.format())
            fmt.setBottomPadding(points)
            cell.setFormat(fmt)

    def set_row_extra_space(self, table, row, points):
        """Keep row height automatic, with optional extra empty space.

        Qt tables have no per-row height API. Cell bottom padding
        is native, undoable, and doesn't hide text inside the row.
        All cells in the row move together.
        """
        if table is None or not 0 <= row < table.rows():
            return
        points = max(0.0, min(_MAX_ROW_EXTRA, float(points)))
        if abs(points - self.row_extra_space(table, row)) < 0.1:
            return
        self._perform(lambda: self._write_row_extra_space(
            table, row, points), keep_cursor=False)

    def set_column_widths(self, table, widths):
        """Commit a mouse drag as ONE native Undo operation."""
        if table is None or len(widths) != table.columns():
            return
        current = self._percentage_widths(table)
        if current is None or all(
                abs(a - b) < 0.01 for a, b in zip(current, widths)):
            return
        self._perform(
            lambda: self._apply_percentage_widths(table, widths),
            keep_cursor=False)

    def table_properties(self):
        """Precise sizing; both edits share one native Undo transaction."""
        table = self.current()
        if table is None:
            return
        cell = table.cellAt(self.editor.textCursor())
        widths = self._percentage_widths(table)
        if not cell.isValid() or widths is None:
            return
        col, row = cell.column(), cell.row()
        original_extra = self.row_extra_space(table, row)
        dialog = TableSizeDialog(widths[col], original_extra, self.notes)
        # A one-column table fills the entire available width.
        # There is no adjacent column to exchange width with.
        dialog.column.setEnabled(len(widths) > 1)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_row = dialog.row.value()
        new_width = dialog.column.value()
        boundary = col + 1 if col + 1 < len(widths) else col
        new_values = None
        if boundary > 0:
            movement = ((new_width - widths[col]) if boundary == col + 1
                        else widths[col] - new_width)
            new_values = resize_adjacent_percentages(
                widths, boundary, movement, min_percent=2.0)
        row_changed = abs(new_row - original_extra) > 0.1
        col_changed = (new_values is not None and any(
            abs(x - y) > 0.1 for x, y in zip(widths, new_values)))
        if not row_changed and not col_changed:
            return

        def apply():
            if row_changed:
                self._write_row_extra_space(table, row, new_row)
            if col_changed:
                self._apply_percentage_widths(table, new_values)

        self._perform(apply, keep_cursor=False)

    def change_table_indent(self, change: int) -> bool:
        """Move the table horizontally as ONE native Undoable edit.

        A QTextTable is also a QTextFrame. Its frame format has
        a left margin, independent of the paragraphs in its cells.
        This avoids changing any cell's own indentation or fonts.

        Negative changes move the table back toward the page's
        left margin. We cannot outdent beyond the page itself.
        """
        table = self.current()
        if not _live_table(table):
            return False
        original = table.format()
        old = max(0.0, float(original.leftMargin()))
        requested = old + (_TABLE_INDENT_STEP if change > 0
                           else -_TABLE_INDENT_STEP)
        target = max(0.0, min(_MAX_TABLE_INDENT, requested))
        if abs(target - old) < 0.01:
            return False

        def apply():
            fmt = table.format()
            # A frame margin shifts its contents without changing
            # the user's existing table alignment or cell styles.
            fmt.setLeftMargin(target)
            table.setFormat(fmt)

        self._perform(apply)
        return True

    def indent_table_right(self):
        """Increase the whole-table left margin by 18 logical pixels."""
        return self.change_table_indent(+1)

    def outdent_table_left(self):
        """Undo one table-indentation level, never past zero."""
        return self.change_table_indent(-1)

    def initialise_percentage_widths(self):
        """Opt an older imported table into safe proportional sizing.

        Some pasted HTML tables have no native percentage widths.
        Never silently rewrite those tables while opening a note.
        This explicit menu action makes all columns equally wide,
        and the change is a single native Undo transaction.
        """
        table = self.current()
        if not _live_table(table):
            return
        if self._percentage_widths(table) is not None:
            return
        self.equalise_columns(table=table)

    @staticmethod
    def _table_has_no_content(table):
        """Check the text and embedded objects in each *real* cell.

        A table with empty paragraphs is empty. But inline images,
        spaces mixed with real content, and hidden object markers
        count as user content and must not be silently discarded.
        """
        if not _live_table(table):
            return False
        visited = set()
        for row in range(table.rows()):
            for col in range(table.columns()):
                cell = table.cellAt(row, col)
                if not cell.isValid():
                    return False
                start = cell.firstCursorPosition()
                end = cell.lastCursorPosition()
                if start.position() in visited:
                    continue
                visited.add(start.position())
                probe = QTextCursor(start)
                probe.setPosition(end.position(),
                                  QTextCursor.MoveMode.KeepAnchor)
                text = probe.selectedText().strip(' \t\r\n\u00a0\u2029')
                if text:
                    return False
        return True

    def delete_table(self):
        """Remove the WHOLE native table in one Undoable operation.

        Qt documents that removing every row also removes the table.
        We store the location as an integer before the delete;
        afterwards the old QTextTable Python wrapper is invalid.
        We therefore never access the table again after removal.
        """
        table = self.current()
        if not _live_table(table):
            marker = getattr(self.editor, '_table_selected_range', None)
            table = (_table_at_position(self.editor, marker[0])
                     if marker else None)
        if not _live_table(table):
            return False
        rows = table.rows()
        position = _table_position(table)
        if not rows or position is None:
            return False

        self.editor.clear_table_interaction()
        self.editor._table_selected_range = None

        def apply():
            # This deletes the frame AND its cells, not just text.
            table.removeRows(0, rows)
            document = self.editor.document()
            point = QTextCursor(document)
            point.setPosition(max(0, min(
                position - 1, document.characterCount() - 1)))
            self.editor.setTextCursor(point)

        self._perform(apply, keep_cursor=False)
        return True

    def delete_empty_table_at_caret(self, *, backward=True):
        """Allow a natural Backspace exit from a fully empty table.

        We refuse if any cell contains text or an embedded image.
        We also support Delete on the entire table selection made
        by its corner handle. A normal cell's Delete still edits text.
        """
        cursor = self.editor.textCursor()
        table = cursor.currentTable()
        # A corner click creates a remembered selection range.
        # Delete should not remove a table merely because some
        # cells' text happens to be selected independently.
        selected_range = getattr(
            self.editor, '_table_selected_range', None)
        if not _live_table(table) and selected_range is not None:
            table = _table_at_position(self.editor, selected_range[0])
        if not _live_table(table):
            return False
        actual_range = (cursor.selectionStart(),
                        cursor.selectionEnd())
        selected_by_corner = (
            selected_range is not None
            and _table_position(table) == selected_range[0]
            and actual_range == selected_range[1:])
        # A 1x1 table may contain an empty cell. The corner handle
        # still counts as selecting the table even if Qt reports no
        # ordinary text selection for that empty cell.
        if selected_by_corner:
            return self.delete_table()
        if cursor.hasSelection():
            # PySide follows Qt's order: first row, row count,
            # first column, column count (NOT row, column, rows,
            # columns). This also recognises keyboard cell selects.
            selected = (tuple(cursor.selectedTableCells())
                        if cursor.hasComplexSelection() else ())
            selected_all_cells = selected == (
                0, table.rows(), 0, table.columns())
            if selected_all_cells:
                return self.delete_table()
            return False
        if not backward:
            return False
        first = table.cellAt(0, 0).firstCursorPosition()
        if cursor.position() != first.position():
            return False
        if not self._table_has_no_content(table):
            return False
        return self.delete_table()

    def remove_row(self):
        """Delete precisely one row; keep the rest of the table intact.

        The content is recoverable through this tab's native Undo
        stack, but is no longer present in the current saved HTML.
        """
        table = self.current()
        if table is None or table.rows() <= 1:
            return
        cell = table.cellAt(self.editor.textCursor())
        if not cell.isValid():
            return
        target_row = cell.row()
        target_col = cell.column()
        if not self._safe_to_delete(table, 'row', target_row):
            self._explain_merged_delete()
            return

        def apply():
            table.removeRows(target_row, 1)
            # The deleted cell no longer exists. Move to a survivor
            # instead of restoring an invalid caret after the edit.
            survivor = table.cellAt(
                min(target_row, table.rows() - 1),
                min(target_col, table.columns() - 1))
            if survivor.isValid():
                self.editor.setTextCursor(
                    survivor.firstCursorPosition())

        self._perform(apply, keep_cursor=False)

    def remove_column(self):
        """Delete precisely one column without resetting custom widths."""
        table = self.current()
        if table is None or table.columns() <= 1:
            return
        cell = table.cellAt(self.editor.textCursor())
        if not cell.isValid():
            return
        target_col = cell.column()
        target_row = cell.row()
        if not self._safe_to_delete(table, 'column', target_col):
            self._explain_merged_delete()
            return
        widths = self._percentage_widths(table)

        def apply():
            table.removeColumns(target_col, 1)
            if widths is not None:
                # Keep every surviving column's relative width.
                new_widths = list(widths)
                new_widths.pop(target_col)
                self._apply_percentage_widths(table, new_widths)
            survivor = table.cellAt(
                min(target_row, table.rows() - 1),
                min(target_col, table.columns() - 1))
            if survivor.isValid():
                self.editor.setTextCursor(
                    survivor.firstCursorPosition())

        self._perform(apply, keep_cursor=False)

    def equalise_columns(self, *, preserve=True, table=None):
        table = table if table is not None else self.current()
        if table is None:
            return

        def apply():
            fmt = table.format()
            fmt.setColumnWidthConstraints([
                QTextLength(QTextLength.Type.PercentageLength,
                            100.0 / table.columns())
                for _ in range(table.columns())
            ])
            table.setFormat(fmt)

        if preserve:
            self._perform(apply)
        else:
            apply()

    def set_cell_padding(self, pixels: float):
        """Change spacing INSIDE cells, leaving table borders alone."""
        table = self.current()
        if table is None:
            return

        def apply():
            fmt = table.format()
            fmt.setCellPadding(float(pixels))
            table.setFormat(fmt)

        self._perform(apply)

    def toggle_borders(self):
        table = self.current()
        if table is None:
            return

        def apply():
            fmt = table.format()
            fmt.setBorder(0.0 if fmt.border() else 1.0)
            table.setFormat(fmt)

        self._perform(apply)

    def toggle_header(self):
        table = self.current()
        if table is None:
            return

        def apply():
            fmt = table.format()
            fmt.setHeaderRowCount(0 if fmt.headerRowCount() else 1)
            table.setFormat(fmt)

        self._perform(apply)

    def _selected_cells(self):
        """Get Qt's real rectangular selection, if one exists."""
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            return None
        result = cursor.selectedTableCells()
        if not result:
            return None
        # Qt returns firstRow, numRows, firstColumn, numColumns.
        row, rows, col, cols = result
        if row < 0 or col < 0 or rows * cols < 2:
            return None
        # mergeCells expects row, column, number of rows, columns.
        return (row, col, rows, cols)

    def merge_selected_cells(self):
        table = self.current()
        selected = self._selected_cells()
        if table is None or selected is None:
            return
        self._perform(lambda: table.mergeCells(*selected))

    def split_cell(self):
        table = self.current()
        if table is None:
            return
        cell = table.cellAt(self.editor.textCursor())
        if not cell.isValid():
            return
        if cell.rowSpan() <= 1 and cell.columnSpan() <= 1:
            return
        self._perform(lambda: table.splitCell(
            cell.row(), cell.column(), cell.rowSpan(), cell.columnSpan()))

    def handle_tab(self, backwards=False):
        """Move among cells; at the end, create one new row.

        Tab outside a table stays under Qt's ordinary behaviour.
        We never use Tab for list indentation in Yomu Note.
        """
        table = self.current()
        if table is None:
            return False
        cell = table.cellAt(self.editor.textCursor())
        if not cell.isValid():
            return False

        # A merged cell may cover several grid positions. We only
        # visit each real cell once, based on its document position.
        cells = []
        visited = set()
        for row in range(table.rows()):
            for col in range(table.columns()):
                candidate = table.cellAt(row, col)
                if not candidate.isValid():
                    continue
                position = candidate.firstCursorPosition().position()
                if position not in visited:
                    cells.append(candidate)
                    visited.add(position)
        current_pos = cell.firstCursorPosition().position()
        index = next((i for i, item in enumerate(cells)
                      if item.firstCursorPosition().position() == current_pos), -1)
        if index < 0:
            return False
        target = index - 1 if backwards else index + 1
        if 0 <= target < len(cells):
            self.editor.setTextCursor(cells[target].firstCursorPosition())
            return True
        if backwards:
            return True  # Shift+Tab in the first cell stays there.
        if table.rows() >= _MAX_ROWS:
            return True

        def add_last_row():
            table.appendRows(1)
            final_row = table.rows()-1
            self._clear_cell_spacing(
                table, ((final_row, col)
                        for col in range(table.columns())))
            self.editor.setTextCursor(
                table.cellAt(final_row, 0).firstCursorPosition())

        self._perform(add_last_row, keep_cursor=False)
        return True


def table_guide_geometry(editor, table):
    """Read the table outline and cell boundaries in VIEWPORT pixels.

    Qt's public Python API exposes the overall table rectangle,
    but not a rectangle per cell. This helper uses the real Qt
    frame position and saved column widths; no text-cursor X
    coordinate is used for the column boundaries.

    Qt's layout rectangles are in DOCUMENT coordinates.
    The scrollbars translate them into VIEWPORT coordinates.
    Never derive that translation from a text caret: its X
    position changes when a cell is centre/right aligned.

    Row boundaries use actual block positions from Qt, with
    the same content inset removed from each row.
    """
    if (not _live_table(table) or table.rows() < 1 or table.columns() < 1 or
            table.rows() > _MAX_ROWS or table.columns() > _MAX_COLUMNS):
        return None
    layout = editor.document().documentLayout()
    first = table.cellAt(0, 0)
    if not first.isValid():
        return None
    first_cursor = first.firstCursorPosition()
    block_rect = layout.blockBoundingRect(first_cursor.block())
    # Document and viewport share their X/Y axes, except for
    # scrolling. A caret's X is NOT a safe origin because text
    # alignment moves it within a cell, not the table itself.
    dx = -editor.horizontalScrollBar().value()
    dy = -editor.verticalScrollBar().value()
    frame = layout.frameBoundingRect(table).translated(dx, dy)
    if not frame.isValid() or frame.isEmpty():
        return None
    fmt = table.format()
    constraints = fmt.columnWidthConstraints()
    if (len(constraints) != table.columns() or
            any(item.type() != QTextLength.Type.PercentageLength or
                item.rawValue() <= 0 for item in constraints)):
        return None
    widths = [item.rawValue() for item in constraints]
    xs = proportional_column_edges(frame.left(), frame.right(), widths)
    if not xs:
        return None

    # The first text block starts some pixels INSIDE the top cell.
    # Reuse that offset when finding the starts of later rows.
    first_text = block_rect.top() + dy
    content_inset = first_text - frame.top()
    ys = [frame.top()] + [None] * (table.rows() - 1) + [frame.bottom()]
    for row in range(1, table.rows()):
        for col in range(table.columns()):
            cell = table.cellAt(row, col)
            if not cell.isValid() or cell.row() != row:
                continue
            cell_rect = layout.blockBoundingRect(
                cell.firstCursorPosition().block())
            ys[row] = cell_rect.top() + dy - content_inset
            break

    # An entirely merged row has no independent border.
    # Interpolation is only used for nearby vertical segments;
    # the merged-cell owner map hides nonexistent horizontal edges.
    for row in range(1, table.rows()):
        if ys[row] is not None:
            continue
        prev = row - 1
        following = row + 1
        while prev > 0 and ys[prev] is None:
            prev -= 1
        while following < table.rows() and ys[following] is None:
            following += 1
        if following <= table.rows():
            ys[row] = ys[prev] + (
                ys[following] - ys[prev]) * (row - prev) / (following - prev)
    if (any(y is None for y in ys) or
            any(ys[i] > ys[i + 1] for i in range(len(ys) - 1))):
        return None
    return (frame, xs, ys)


def table_corner_rect(frame):
    """The small square just outside the table's top-left corner."""
    return QRectF(frame.left() - 12.0, frame.top() - 12.0, 11.0, 11.0)


def table_interaction_hit(editor, position):
    """Hit-test fresh Qt tables, never a saved PySide wrapper.

    The old code put a QTextTable in _table_hover. When Qt
    discarded the C++ object, repainting raised RuntimeError
    indefinitely. Stored positions avoid that lifetime problem.
    """
    hovered = editor.cursorForPosition(
        position.toPoint()).currentTable()
    active = editor.textCursor().currentTable()
    tables = []
    positions = set()
    for table in (hovered, active, _hover_table(editor)):
        position_in_document = _table_position(table)
        if (position_in_document is not None and
                position_in_document not in positions):
            positions.add(position_in_document)
            tables.append(table)
    for table in tables:
        geometry = table_guide_geometry(editor, table)
        if geometry is None:
            continue
        frame, xs, ys = geometry
        if table_corner_rect(frame).contains(position):
            return ('select', table, 0, geometry)
        if not frame.adjusted(-7, -7, 7, 7).contains(position):
            continue
        x, y = position.x(), position.y()
        if frame.top() <= y <= frame.bottom():
            index = closest_table_edge(x, xs, tolerance=7.0)
            if index is not None:
                return ('column', table, index, geometry)
        if frame.left() <= x <= frame.right():
            index = closest_table_edge(
                y, ys, tolerance=7.0, include_final=True)
            if index is not None:
                if index < table.rows():
                    owners = TableTools._owners(table)
                    if any(owners[index-1][col] == owners[index][col]
                           for col in range(table.columns())):
                        continue
                return ('row', table, index, geometry)
    return None


def paint_table_guides(editor, painter: QPainter):
    """Paint TEMPORARY outlines that never enter the saved HTML.

    Permanent borders come from Qt's native table format.
    For a borderless table, use the same outer table rectangle,
    with one shared line per internal boundary. A little cell
    padding keeps the guides away from the letters.
    """
    # Always resolve from the CURRENT document. No stale Qt object
    # may survive as a hover/drag field across Undo or reformatting.
    table = (_hover_table(editor) or
             editor.textCursor().currentTable())
    if not _live_table(table):
        return
    geometry = table_guide_geometry(editor, table)
    if geometry is None:
        return
    frame, xs, ys = geometry
    borderless = table.format().border() <= 0
    if not borderless and not getattr(editor, '_table_drag', None):
        # The native permanent border already shows the grid.
        # We still show a little selection handle at the corner.
        pass

    painter.save()
    try:
        painter.setClipRect(editor.viewport().rect())
        accent = editor.palette().highlight().color()
        accent.setAlpha(180)
        if borderless:
            grid_color = editor.palette().mid().color()
            grid_color.setAlpha(175)
            pen = QPen(grid_color, 1.0, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # Slightly inset helps the outline sit where Qt would
            # draw a native 1px border, rather than over its text.
            painter.drawRect(frame.adjusted(0.5, 0.5, -0.5, -0.5))
            for x0, y0, x1, y1 in grid_segments(
                    TableTools._owners(table), xs, ys):
                painter.drawLine(round(x0), round(y0),
                                 round(x1), round(y1))

        # A small accessible corner control selects every cell.
        # It is a viewport drawing, not part of the document.
        corner = table_corner_rect(frame)
        if corner.intersects(editor.viewport().rect()):
            painter.setPen(QPen(accent, 1.0))
            knob = editor.palette().base().color()
            painter.setBrush(knob)
            painter.drawRoundedRect(corner, 2.0, 2.0)
            painter.drawLine(
                round(corner.left()+3), round(corner.top()+3),
                round(corner.right()-3), round(corner.bottom()-3))

        drag = getattr(editor, '_table_drag', None)
        if drag and _drag_table(editor, drag) is not None and (
                drag['table_position'] == _table_position(table)):
            pen = QPen(accent, 2.0, Qt.PenStyle.SolidLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            if drag['kind'] == 'column':
                adjusted = proportional_column_edges(
                    frame.left(), frame.right(), drag['preview'])
                if adjusted:
                    x = adjusted[drag['index']]
                    painter.drawLine(round(x), round(frame.top()),
                                     round(x), round(frame.bottom()))
            elif drag['kind'] == 'row':
                y = ys[drag['index']] + drag['delta']
                painter.drawLine(round(frame.left()), round(y),
                                 round(frame.right()), round(y))
    finally:
        painter.restore()
