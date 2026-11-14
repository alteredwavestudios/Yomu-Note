"""Rich-text notes pane with page links, formatting, and paragraph tools."""
from __future__ import annotations
import sys
from PySide6.QtCore import Qt, Signal, QSignalBlocker, QEvent, QPropertyAnimation, QEasingCurve, QAbstractAnimation, QTimer, QPoint, QPointF
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QPainter, QTextCharFormat, QTextFormat, QTextListFormat, QTextBlockFormat, QTextFrameFormat, QTextCursor, QTextDocument, QShortcut, QSyntaxHighlighter, QFontMetricsF, QCursor
from .ui import WrapBar, FormattingColourButton, line_icon
from .notes_layout import NotesPageSetup, pt_to_px, fitted_margins
from .notes_layout_dialog import ParagraphSpacingDialog
from .notes_spacing import add_spacing_metadata, split_spacing_metadata
from .notes_tables import TableTools, paint_table_guides
from .platform_shortcuts import IS_MAC, PRIMARY, ALT, docs_shortcut, shortcut_label
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit, QFontComboBox, QToolButton, QDialog,
    QSpinBox, QComboBox, QInputDialog, QColorDialog, QMessageBox, QApplication, QMenu,
    QHBoxLayout, QLineEdit, QPushButton, QToolButton,
)


class NotesViewZoomHighlighter(QSyntaxHighlighter):
    """Enlarge or shrink the *display* of notes without editing saved text.

    QTextEdit.zoomIn only affects the editor's default font, so it appears to
    do nothing when imported or formatted notes have explicit font sizes.

    QSyntaxHighlighter paints additional character formatting on screen, but
    deliberately does NOT write it into QTextDocument, HTML, or undo history.
    Unlike replacing document HTML on every zoom, this also preserves the
    user's cursor, hyperlinks, paragraph styles, and existing undo stack.
    """

    def __init__(self, document):
        super().__init__(document)
        self._view_scale = 1.0

    def set_view_scale(self, scale: float):
        """Repaint visible text at a new magnification, without saving it."""
        scale = max(0.6, min(2.6, float(scale)))
        if abs(scale - self._view_scale) < 0.0001:
            return
        self._view_scale = scale
        self.rehighlight()

    def highlightBlock(self, text):
        """Overlay scaled sizes on runs of text, retaining all other styles."""
        if abs(self._view_scale - 1.0) < 0.0001:
            return
        block = self.currentBlock()
        document = self.document()
        if not block.isValid() or document is None:
            return
        default_size = document.defaultFont().pointSizeF()
        if default_size <= 0:
            default_size = 13.0
        # Iterate the block's rich-text fragments, not individual characters;
        # this keeps the operation inexpensive even for lengthy notes.
        for iterator in block:
            run = iterator.fragment()
            if run.isValid() and run.length() > 0:
                original = run.charFormat()
                point_size = original.fontPointSize()
                if point_size <= 0:
                    # A few imported HTML spans specify sizes in pixels.
                    # QTextCharFormat has no fontPixelSize() convenience method:
                    # inspect the underlying QTextFormat property instead.
                    if original.hasProperty(QTextFormat.Property.FontPixelSize):
                        pixel_size = float(original.property(QTextFormat.Property.FontPixelSize))
                        if pixel_size > 0:
                            point_size = pixel_size * 72.0 / 96.0
                if point_size <= 0:
                    block_point_size = block.charFormat().fontPointSize()
                    point_size = block_point_size if block_point_size > 0 else default_size
                overlay = QTextCharFormat()
                overlay.setFontPointSize(max(4.0, min(160.0, point_size * self._view_scale)))
                self.setFormat(run.position() - block.position(), run.length(), overlay)


# Imported HTML and pasted notes often contain visually empty paragraphs
# holding spaces, NBSPs, zero-width marks, or direction-control characters.
# Qt still sees these as text fragments, so an empty-string-only check misses
# them and the previous v0.4.5b empty-line height fix never runs.
_INVISIBLE_LINE_MARKS = frozenset('\u00ad\u034f\u061c\u180e\u200b\u200c\u200d\u200e\u200f\u2060\u2061\u2062\u2063\u2064\u2066\u2067\u2068\u2069\ufeff')


def _is_visually_blank_paragraph(text: str) -> bool:
    # No visible glyphs, including pasted whitespace.
    return all(char.isspace() or char in _INVISIBLE_LINE_MARKS for char in text)


# QTextBlockFormat is Qt's paragraph data structure.
# UserProperty is reserved for application-specific values.
# We keep a separate flag for each deliberately chosen setting.
# This distinguishes an explicit 0 pt gap from an inherited default.
_SPACING_USER_BASE = int(QTextFormat.Property.UserProperty) + 517
_BEFORE_PT_OVERRIDE = _SPACING_USER_BASE
_AFTER_PT_OVERRIDE = _SPACING_USER_BASE + 1
_LINE_MULTIPLIER_OVERRIDE = _SPACING_USER_BASE + 2
_SPACING_PROPERTIES = {
    'before_pt': _BEFORE_PT_OVERRIDE,
    'after_pt': _AFTER_PT_OVERRIDE,
    'line': _LINE_MULTIPLIER_OVERRIDE,
}


class LinkTextEdit(QTextEdit):
    linkActivated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.link_tooltip_resolver = None
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        # These are VISUAL interaction states only. No table content
        # is changed until the user finishes dragging a divider.
        self._table_drag = None
        self._table_hover_position = None
        # Only the corner handle marks an entire table for Delete.
        # Ordinary selected text inside a cell must remain safe.
        self._table_selected_range = None
        self._table_edit_serial = 0
        # A timer is a safety net if Windows never delivers mouse release.
        # It never holds a mouse grab or changes document contents.
        self._table_drag_watchdog = QTimer(self)
        self._table_drag_watchdog.setInterval(80)
        self._table_drag_watchdog.timeout.connect(
            self._finish_table_drag_if_mouse_released)
        # Any text/format edit may destroy an old C++ table.
        # Reset mouse state so painting never touches a dead wrapper.
        self.document().contentsChange.connect(
            self._on_table_document_changed)
        self._wheel_animation = QPropertyAnimation(self.verticalScrollBar(), b'value', self)
        self._wheel_animation.setDuration(190)
        self._wheel_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._resize_anchor = None
        self._resize_restore_timer = QTimer(self)
        self._resize_restore_timer.setSingleShot(True)
        self._resize_restore_timer.setInterval(0)
        self._resize_restore_timer.timeout.connect(self._restore_resize_anchor)

    def clear_table_interaction(self):
        """Release a cancelled resize and erase its preview line.

        A drag belongs to the viewport, not the saved document.
        Always release mouse capture, even if the table vanished.
        """
        self._table_drag = None
        self._table_hover_position = None
        self._table_drag_watchdog.stop()
        # Never call grabMouse/releaseMouse here. Qt already manages
        # implicit mouse capture for a normal button press. Explicit
        # viewport capture caused the Windows editor to become stuck.
        self.viewport().unsetCursor()
        self.viewport().update()

    def _finish_table_drag_if_mouse_released(self):
        """Recover safely when release occurred outside the viewport.

        Qt normally sends mouse release to the widget that was
        pressed. A lost event must never keep a guide or lock the UI.
        We try to commit at the present pointer location, but if
        that fails the drag is cancelled and the notebook remains safe.
        """
        if self._table_drag is None:
            self._table_drag_watchdog.stop()
            return
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            return
        handler = getattr(self, 'table_pointer_handler', None)
        try:
            if handler is not None:
                cursor_position = self.viewport().mapFromGlobal(QCursor.pos())
                handler('release', QPointF(cursor_position))
        finally:
            if self._table_drag is not None:
                self.clear_table_interaction()

    def _on_table_document_changed(self, *_):
        """Invalidate temporary handles when Qt changes document objects."""
        self._table_edit_serial += 1
        self._table_selected_range = None
        if self._table_drag is not None or self._table_hover_position is not None:
            self.clear_table_interaction()

    def capture_view_state(self):
        # Capture scrollbar value and visible-block anchor before a layout-changing edit.
        bar = self.verticalScrollBar()
        anchor = self.cursorForPosition(QPoint(8, min(8, max(0, self.viewport().height()-1))))
        return {
            'scroll': bar.value(),
            'cursor': QTextCursor(self.textCursor()),
            'anchor': QTextCursor(anchor),
            'anchor_top': self.cursorRect(anchor).top(),
            'had_focus': self.hasFocus(),
        }

    def restore_view_state(self, state, *, restore_cursor=True):
        """Keep the same visible text at the same viewport Y after reflow."""
        if not state:
            return
        self._wheel_animation.stop()
        cursor = state.get('cursor')
        if restore_cursor and cursor is not None and not cursor.isNull():
            # Editing commands preserve selection; a resize leaves caret untouched.
            self.setTextCursor(QTextCursor(cursor))
        anchor = state.get('anchor')
        bar = self.verticalScrollBar()
        if anchor is not None and not anchor.isNull():
            # Use the CURRENT scrollbar: the old value + new displacement double-counted jumps.
            displacement = self.cursorRect(anchor).top() - int(state.get('anchor_top', 0))
            bar.setValue(max(bar.minimum(), min(bar.maximum(), bar.value() + displacement)))
        else:
            bar.setValue(max(bar.minimum(), min(bar.maximum(), int(state.get('scroll', 0)))))
        if restore_cursor and state.get('had_focus'):
            self.setFocus()

    def preserve_view_state(self, callback, *, restore_cursor=True):
        """Keep the reading position stable through a layout-changing edit.

        Most formatting edits must keep the original selection.
        Table insertion is different: the caret must move INTO
        the first cell, not back to where the table was inserted.
        """
        state = self.capture_view_state()
        callback()
        self.restore_view_state(state, restore_cursor=restore_cursor)
        QTimer.singleShot(
            0, lambda s=state, c=restore_cursor:
            self.restore_view_state(s, restore_cursor=c))

    def _restore_resize_anchor(self):
        # A window resize restores only the reading line, never moves the editing caret.
        state = self._resize_anchor
        self._resize_anchor = None
        if state is not None:
            self.restore_view_state(state, restore_cursor=False)

    def resizeEvent(self, event):
        # Preserve the original reading anchor throughout one resize burst.
        if self._resize_anchor is None and self.isVisible():
            self._resize_anchor = self.capture_view_state()
        super().resizeEvent(event)
        handler = getattr(self, 'page_setup_resize_handler', None)
        if handler is not None:
            handler()
        if self._resize_anchor is not None:
            self._resize_restore_timer.start()

    def contextMenuEvent(self, event):
        """Keep right-click Undo/Redo in the shared notebook history.

        QTextEdit normally creates its own Undo and Redo menu actions.
        Those actions bypass Yomu's history of notes, annotations,
        pages, and tabs. Mixing the two histories can undo the wrong
        operation or make Redo point at an unrelated change.

        We keep Qt's familiar Cut, Copy and Paste menu, replacing only
        its native Undo and Redo actions with shared-history actions.
        """
        # Right-clicking another cell should open THAT cell's tools.
        # Never collapse a deliberate multi-cell selection.
        pointed = self.cursorForPosition(event.pos())
        if not self.textCursor().hasSelection():
            self.setTextCursor(pointed)

        handler = getattr(self, 'history_key_handler', None)
        if handler is None:
            # Standalone editor previews also need table controls,
            # even before a notebook's shared history is attached.
            provider = getattr(self, 'table_context_provider', None)
            if (provider is not None and
                    self.textCursor().currentTable() is not None):
                local_menu = self.createStandardContextMenu()
                try:
                    local_menu.addSeparator()
                    local_menu.addMenu(provider(local_menu))
                    local_menu.exec(event.globalPos())
                finally:
                    local_menu.deleteLater()
            else:
                super().contextMenuEvent(event)
            return

        menu = self.createStandardContextMenu()
        try:
            for action in tuple(menu.actions()):
                # The ampersand marks a keyboard accelerator in Qt menus.
                # Strip it before comparing the English action label.
                label = action.text().replace('&', '').split('\t')[0].strip()
                if label.lower() in ('undo', 'redo'):
                    menu.removeAction(action)
            first = menu.actions()[0] if menu.actions() else None
            redo = QAction('Redo', menu)
            redo.triggered.connect(lambda _=False: handler(True))
            if first is not None:
                menu.insertAction(first, redo)
            else:
                menu.addAction(redo)
            undo = QAction('Undo', menu)
            undo.triggered.connect(lambda _=False: handler(False))
            menu.insertAction(redo, undo)
            if first is not None:
                menu.insertSeparator(first)
            availability = getattr(self, 'history_availability', None)
            if callable(availability):
                can_undo, can_redo = availability()
                undo.setEnabled(bool(can_undo))
                redo.setEnabled(bool(can_redo))

            # Reuse the toolbar's commands so row/column changes,
            # formatting and Undo all follow the same code path.
            provider = getattr(self, 'table_context_provider', None)
            if (provider is not None and
                    self.textCursor().currentTable() is not None):
                menu.addSeparator()
                menu.addMenu(provider(menu))
            menu.exec(event.globalPos())
        finally:
            menu.deleteLater()

    def wheelEvent(self, event):
        """Keep touchpad momentum native, gently ease desktop wheel notches."""
        if (not event.pixelDelta().isNull()
                or event.modifiers() != Qt.KeyboardModifier.NoModifier):
            self._wheel_animation.stop()
            super().wheelEvent(event)
            return
        steps = event.angleDelta().y() / 120.0
        if not steps:
            super().wheelEvent(event)
            return
        bar = self.verticalScrollBar()
        base = (int(self._wheel_animation.endValue())
                if self._wheel_animation.state() == QAbstractAnimation.State.Running
                else bar.value())
        target = max(bar.minimum(), min(bar.maximum(), round(base - steps * 62)))
        self._wheel_animation.stop()
        self._wheel_animation.setStartValue(bar.value())
        self._wheel_animation.setEndValue(target)
        self._wheel_animation.start()
        event.accept()

    def paintEvent(self, event):
        # Native Qt draws the text and permanent table borders.
        # We draw transient guides, a corner handle, and drag preview
        # afterwards. These are NEVER saved into the notes HTML.
        super().paintEvent(event)
        if ((self.hasFocus() and
             self.textCursor().currentTable() is not None) or
                self._table_hover_position is not None or
                self._table_drag is not None):
            painter = QPainter(self.viewport())
            try:
                try:
                    paint_table_guides(self, painter)
                except RuntimeError as exc:
                    # A C++ object can disappear during re-layout.
                    # This guard is a last resort, not the fix:
                    # the mouse state stores positions, not objects.
                    if 'already deleted' not in str(exc):
                        raise
                    self.clear_table_interaction()
            finally:
                painter.end()

    def setHtml(self, text):
        # A new document invalidates pointers to old Qt table cells.
        # Drop those temporary viewport references before loading.
        self.clear_table_interaction()
        self._table_selected_range = None
        super().setHtml(text)

    def setPlainText(self, text):
        # The live text owns the tables; hover state owns nothing.
        # Reset it whenever all text is replaced.
        self.clear_table_interaction()
        self._table_selected_range = None
        super().setPlainText(text)

    def leaveEvent(self, event):
        # Hiding guides on mouse exit does not edit the document.
        if self._table_drag is None:
            self._table_hover_position = None
            self.viewport().unsetCursor()
            self.viewport().update()
        super().leaveEvent(event)

    def hideEvent(self, event):
        # Switching tabs hides this notes editor. Never leave a drag
        # active in a hidden tab, even if the mouse button is held.
        self.clear_table_interaction()
        self._table_selected_range = None
        super().hideEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.viewport().update()

    def focusOutEvent(self, event):
        # Guides are editing aids, so hide them on focus loss.
        # Real permanent borders remain visible in the document.
        self.clear_table_interaction()
        super().focusOutEvent(event)
        self.viewport().update()

    def mousePressEvent(self, event):
        # On a divider, start a preview drag without editing the
        # document yet. One native Undo step is created on release.
        if event.button() == Qt.MouseButton.LeftButton:
            handler = getattr(self, 'table_pointer_handler', None)
            if handler is not None and handler('press', event.position()):
                # This timer cannot grab the mouse or block the event loop.
                if self._table_drag is not None:
                    self._table_drag_watchdog.start()
                event.accept()
                return
        # A normal click is no longer a whole-table selection.
        # The corner-handle path returns above before this point.
        self._table_selected_range = None
        super().mousePressEvent(event)
        # A click outside every table closes the temporary guides.
        # The document's stored borders are never changed here.
        if self.textCursor().currentTable() is None:
            self._table_hover_position = None
            self.viewport().update()

    def mouseMoveEvent(self, event):
        # If a release was missed, complete it instead of leaving a
        # permanent resize line and intercepting unrelated clicks.
        if (self._table_drag is not None and
                not (event.buttons() & Qt.MouseButton.LeftButton)):
            self._finish_table_drag_if_mouse_released()
        handler = getattr(self, 'table_pointer_handler', None)
        if (handler is not None and
                (self._table_drag is not None or
                 event.buttons() == Qt.MouseButton.NoButton) and
                handler('move', event.position())):
            event.accept()
            return
        link = self.anchorAt(event.position().toPoint())
        description = (self.link_tooltip_resolver(link)
                       if link and self.link_tooltip_resolver else link)
        if self.cursorForPosition(event.position().toPoint()).currentTable():
            help_text = getattr(self, 'table_hover_help', '')
            description = help_text or description
        self.viewport().setToolTip(description or '')
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if event.key() not in (Qt.Key.Key_Backspace,
                               Qt.Key.Key_Delete):
            self._table_selected_range = None
        # Backspace on a completely EMPTY table's first cell exits
        # the table. Deleting real cell content still needs the
        # explicit "Delete entire table" command or a full selection.
        if (event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete)
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            table_tools = getattr(self, 'table_tools', None)
            if table_tools is not None and table_tools.delete_empty_table_at_caret(
                    backward=(event.key() == Qt.Key.Key_Backspace)):
                event.accept()
                return
        if (event.key() == Qt.Key.Key_Escape and
                self._table_drag is not None):
            # Escape cancels a resize before it affects saved data.
            self.clear_table_interaction()
            event.accept()
            return
        # Follow the running OS (not the keyboard's printed symbols):
        # Windows/Linux Ctrl+Backspace and Ctrl+Delete remove ONE word.
        # On macOS Qt maps Command to ControlModifier and Option to
        # AltModifier; Option+Delete/Backspace removes one word, while
        # Command+Delete/Backspace removes text to the line edge.
        # Never remove an entire paragraph for a word-delete shortcut.
        mods = event.modifiers()
        key = event.key()

        # Tab only navigates real table cells. It does NOT indent
        # normal text or lists; those retain Ctrl/Cmd+[ and ].
        if (key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
                and not (mods & (Qt.KeyboardModifier.ControlModifier |
                               Qt.KeyboardModifier.AltModifier))):
            navigate = getattr(self, 'table_tab_handler', None)
            if (navigate is not None and navigate(
                    backwards=(key == Qt.Key.Key_Backtab or
                               bool(mods & Qt.KeyboardModifier.ShiftModifier)))):
                event.accept()
                return

        # All editing surfaces share the notebook history, including while
        # this QTextEdit owns keyboard focus. Do not let native QTextEdit
        # consume Ctrl/Command+Z before the unified dispatcher sees it.
        history_handler = getattr(self, 'history_key_handler', None)
        if history_handler is not None and bool(mods & Qt.KeyboardModifier.ControlModifier) and not bool(mods & Qt.KeyboardModifier.AltModifier):
            if key == Qt.Key.Key_Z:
                history_handler(bool(mods & Qt.KeyboardModifier.ShiftModifier))
                event.accept()
                return
            if key == Qt.Key.Key_Y and not bool(mods & Qt.KeyboardModifier.ShiftModifier) and not IS_MAC:
                history_handler(True)
                event.accept()
                return
        is_delete = key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete)
        primary = bool(mods & Qt.KeyboardModifier.ControlModifier)
        option = bool(mods & Qt.KeyboardModifier.AltModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if is_delete and not shift:
            word_delete = (option and not primary) if IS_MAC else (primary and not option)
            line_delete = IS_MAC and primary and not option
            if word_delete or line_delete:
                cursor = self.textCursor()
                if cursor.hasSelection():
                    cursor.removeSelectedText()
                else:
                    operation = (
                        (QTextCursor.MoveOperation.StartOfLine if key == Qt.Key.Key_Backspace
                         else QTextCursor.MoveOperation.EndOfLine) if line_delete else
                        (QTextCursor.MoveOperation.PreviousWord if key == Qt.Key.Key_Backspace
                         else QTextCursor.MoveOperation.NextWord)
                    )
                    # Limit the deletion to this paragraph. A word-delete
                    # should not eat a line break and join paragraphs.
                    start = cursor.position()
                    boundary = (cursor.block().position() if key == Qt.Key.Key_Backspace
                                else cursor.block().position() + cursor.block().length() - 1)
                    if cursor.movePosition(operation, QTextCursor.MoveMode.KeepAnchor):
                        destination = max(boundary, cursor.position()) if key == Qt.Key.Key_Backspace else min(boundary, cursor.position())
                        cursor.setPosition(start)
                        cursor.setPosition(destination, QTextCursor.MoveMode.KeepAnchor)
                        cursor.removeSelectedText()
                self.setTextCursor(cursor)
                event.accept()
                return
        # Return in a list is one Undo operation.
        #
        # Use a cursor at the actual typing position, not document start.
        # An unrelated cursor at position zero can make Qt jump to the top
        # when list spacing changes trigger another layout pass.
        if (key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and mods == Qt.KeyboardModifier.NoModifier
                and self.textCursor().currentList() is not None):
            view = self.capture_view_state()
            previous_position = self.textCursor().block().position()
            writer = QTextCursor(self.textCursor())
            writer.beginEditBlock()
            try:
                super().keyPressEvent(event)
                handler = getattr(self, 'list_return_handler', None)
                if handler is not None:
                    handler([previous_position,
                             self.textCursor().block().position()])
            finally:
                writer.endEditBlock()

            # Restore the reading anchor, but NOT the old caret.
            # The new caret belongs on the newly inserted list item.
            def finish_return():
                self.restore_view_state(view, restore_cursor=False)
                rect = self.cursorRect(self.textCursor())
                if rect.bottom() >= self.viewport().height() or rect.top() < 0:
                    self.ensureCursorVisible()
            finish_return()
            QTimer.singleShot(0, finish_return)
            event.accept()
            return
        # Yomu v0.3.1 hotfix: Qt resets a blank paragraph's typing style
        # on a second Return. Preserve the actual character format and insert
        # a new ordinary paragraph instead. Leave list-item Returns to Qt so
        # pressing Return on an empty list item still exits the list.
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            cursor = self.textCursor()
            if not cursor.hasSelection() and cursor.currentList() is None:
                previous_format = QTextCharFormat(self.currentCharFormat())
                if previous_format.isAnchor():
                    previous_format.setAnchor(False)
                    previous_format.setAnchorHref('')
                    previous_format.setFontUnderline(False)
                if cursor.block().text() == '':
                    cursor.beginEditBlock()
                    cursor.insertBlock(cursor.blockFormat(), previous_format)
                    cursor.endEditBlock()
                    self.setTextCursor(cursor)
                    self.setCurrentCharFormat(previous_format)
                    event.accept()
                    return
                earlier_block = cursor.blockNumber()
                super().keyPressEvent(event)
                if (self.textCursor().blockNumber() != earlier_block
                        and self.textCursor().currentList() is None):
                    self.setCurrentCharFormat(previous_format)
                return
        # Certain layouts report Shift+period as '>' and Shift+comma as '<'.
        # Handling these keys here (before Qt's default editor processing)
        # makes Google Docs-style font-size shortcuts reliable on Windows.
        handler = getattr(self, 'docs_key_handler', None)
        if handler is not None and handler(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseReleaseEvent(self, event):
        """Finish table resizing BEFORE handling ordinary editor clicks.

        Important: there must be only ONE mouseReleaseEvent method.
        A second definition silently replaced this handler in 0.6.7a.
        That left the preview line visible and the mouse captured.
        """
        handler = getattr(self, 'table_pointer_handler', None)
        if (event.button() == Qt.MouseButton.LeftButton and
                self._table_drag is not None):
            try:
                if handler is not None:
                    handler('release', event.position())
            finally:
                # Clean up even if Qt raises while resizing a table.
                if self._table_drag is not None:
                    self.clear_table_interaction()
            event.accept()
            return
        # Cmd-click on macOS; Ctrl-click on Windows/Linux opens links.
        if event.modifiers() & (Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.ControlModifier):
            link = self.anchorAt(event.position().toPoint())
            if link:
                self.linkActivated.emit(link)
                event.accept()
                return
        super().mouseReleaseEvent(event)


class NotesEditor(QWidget):
    """Rich-text notes editor and toolbar owned by a ProjectPane.

    QTextDocument keeps the HTML formatting and its own typing Undo stack.
    Toolbar actions adjust character/block formats via QTextCursor. View
    zoom should never modify HTML or saved font sizes.
    """
    changed = Signal()
    pageLinkClicked = Signal(str)
    externalLinkClicked = Signal(str)
    pageLinkRequested = Signal()
    fontSetAsDefault = Signal(str)
    pageSetupRequested = Signal()

    def __init__(self, parent=None, defaults=None):
        super().__init__(parent)
        self.defaults = defaults or {}
        self._shortcuts = []
        root = QVBoxLayout(self)
        root.setContentsMargins(9, 7, 9, 8)
        root.setSpacing(4)

        heading = QLabel('NOTES  ·  RICH TEXT')
        heading.setObjectName('sectionLabel')
        root.addWidget(heading)

        # TWO compact rows: icons + grouped menus give the editor extra height.
        # Every action has an accessible tooltip including its keyboard shortcut.
        row1 = WrapBar('Font and inline formatting')
        root.addWidget(row1)
        self.font_choice = QFontComboBox()
        self.font_choice.setFontFilters(QFontComboBox.FontFilter.ScalableFonts)
        self.font_choice.setMinimumWidth(82)
        self.font_choice.setMaximumWidth(125)
        self.font_choice.setToolTip('Font family · right-click to set the default font')
        self.font_choice.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.font_choice.customContextMenuRequested.connect(self.font_context_menu)
        row1.addWidget(self.font_choice)
        self.font_size = QSpinBox()
        self.font_size.setRange(7, 120)
        self.font_size.setValue(13)
        self.font_size.setFixedWidth(54)
        self.font_size.setToolTip(f'Font size in points · {docs_shortcut("larger_font")} larger, {docs_shortcut("smaller_font")} smaller')
        row1.addWidget(self.font_size)
        self.bold_action = self._toggle_action(row1, 'B', f'Bold · {docs_shortcut("bold")}', 'bold')
        self.italic_action = self._toggle_action(row1, 'I', f'Italic · {docs_shortcut("italic")}', 'italic')
        self.underline_action = self._toggle_action(row1, 'U̲', f'Underline · {docs_shortcut("underline")}', 'underline')
        self.strike_action = self._toggle_action(row1, 'S̶', f'Strikethrough · {docs_shortcut("strike")}', 'strike')
        self.text_colour_button = FormattingColourButton(highlight=False)
        self.text_colour_button.clicked.connect(self.pick_colour)
        row1.addWidget(self.text_colour_button)
        self.text_highlight_button = FormattingColourButton(highlight=True)
        self.text_highlight_button.clicked.connect(self.pick_highlight)
        row1.addWidget(self.text_highlight_button)

        row2 = WrapBar('Paragraph formatting, links and navigation')
        root.addWidget(row2)
        self.heading_choice = QComboBox()
        self.heading_choice.addItems([
            'Normal', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'Mixed'])
        # Mixed is a display state, not a formatting command.
        self.heading_choice.model().item(7).setEnabled(False)
        self.heading_choice.setFixedWidth(84)
        self.heading_choice.setToolTip('Paragraph style: normal, heading 1–6')
        row2.addWidget(self.heading_choice)

        # Keep alignment and list types behind one icon each, not four or
        # five separate text buttons that squeeze the editing surface.
        alignment_menu = QMenu(self)
        for name, icon_name, value, shortcut in [
            ('Left', 'align-left', Qt.AlignmentFlag.AlignLeft, docs_shortcut('left')),
            ('Centre', 'align-center', Qt.AlignmentFlag.AlignHCenter, docs_shortcut('centre')),
            ('Right', 'align-right', Qt.AlignmentFlag.AlignRight, docs_shortcut('right')),
            ('Justify', 'align-justify', Qt.AlignmentFlag.AlignJustify, docs_shortcut('justify')),
        ]:
            action = alignment_menu.addAction(line_icon(icon_name), f'{name}  ·  {shortcut}')
            action.triggered.connect(lambda _=False, align=value: self.editor.setAlignment(align))
        row2.addMenuButton('align-left', 'Paragraph alignment · Left / Centre / Right / Justify', alignment_menu)
        list_menu = QMenu(self)
        numbered = list_menu.addAction(line_icon('list-ordered'), f'Numbered list  ·  {docs_shortcut("numbered")}')
        numbered.triggered.connect(lambda: self.make_list(True))
        bulleted = list_menu.addAction(line_icon('list'), f'Bulleted list  ·  {docs_shortcut("bulleted")}')
        bulleted.triggered.connect(lambda: self.make_list(False))
        row2.addMenuButton('list', 'Lists · numbered or bulleted', list_menu)

        # A table is native rich text, not a collection of widgets.
        # Build its menu now; commands find the editor when clicked.
        self.tables = TableTools(self)
        row2.addMenuButton(
            'table',
            f'Tables · Insert {docs_shortcut("insert_table")} · '
            'row/column tools, borders and sizing',
            self.tables.build_menu(self))
        row2.addIconAction('outdent', f'Outdent current list item / paragraph · {docs_shortcut("outdent")}', lambda: self.indent(-1))
        row2.addIconAction('indent', f'Indent current list item / paragraph · {docs_shortcut("indent")}', lambda: self.indent(+1))
        spacing_menu = QMenu(self)
        for value, label in ((1.0, 'Single (1.0×)'), (1.15, 'Default (1.15×)'),
                             (1.5, 'One and a half (1.5×)'), (2.0, 'Double (2.0×)')):
            spacing_menu.addAction(label, lambda checked=False, v=value:
                                   self.set_selected_paragraph_spacing(line_multiplier=v))
        spacing_menu.addSeparator()
        spacing_menu.addAction('Custom paragraph spacing…', self.show_paragraph_spacing)
        spacing_menu.addAction('Use document spacing defaults', self.reset_selected_spacing)
        row2.addMenuButton('line-spacing', 'Line & paragraph spacing', spacing_menu)
        row2.addIconAction('link', f'Insert link to selected page · {docs_shortcut("page_link")}', self.pageLinkRequested.emit)
        # External website links stay available through a shortcut and a menu;
        # a separate always-visible button can be enabled in Preferences.
        self.web_link_action = row2.addIconAction('link', f'Insert website link · {docs_shortcut("web_link")}', self.insert_web_link)
        self.web_link_button = row2.buttons[-1]
        self.web_link_button.setVisible(bool(self.defaults.get('show_web_link', False)))
        more_menu = QMenu(self)
        more_menu.addAction('Notes page setup…', self.pageSetupRequested.emit)
        more_menu.addAction('Jump to last edit', self.jump_to_edit_position)
        more_menu.addSeparator()
        more_menu.addAction('Insert horizontal line', self.insert_horizontal_line)
        more_menu.addAction(f'Insert website hyperlink  ·  {docs_shortcut("web_link")}', self.insert_web_link)
        more_menu.addAction(f'Clear character formatting  ·  {shortcut_label("Ctrl+\\\\")}', self.clear_formatting)
        row2.addMenuButton('more', 'More formatting options and external links', more_menu)
        # View zoom affects the QTextEdit widget's display font, not the font
        # size selected for document text. This zoom isn't written to HTML.
        zoom_out = row2.addIconAction('zoom-out',
                     f'Zoom notes view out · {docs_shortcut("notes_zoom_out")}',
                     lambda: self.zoom_notes(-1))
        zoom_in = row2.addIconAction('zoom-in',
                    f'Zoom notes view in · {docs_shortcut("notes_zoom_in")}',
                    lambda: self.zoom_notes(+1))
        row2.addIconAction('edit-position', 'Jump to last edit position', self.jump_to_edit_position)
        self.jump_edit_button = row2.buttons[-1]
        self.jump_edit_button.setVisible(bool(self.defaults.get('show_jump_edit', False)))
        self._notes_zoom_points = 0
        self._zoom_anchor_token = 0  # cancel delayed alignment from earlier rapid zooms
        self.notes_zoom_label = QLabel('Notes · 100%')
        self.notes_zoom_label.setObjectName('hintLabel')
        self.notes_zoom_label.setMinimumWidth(82)
        self.notes_zoom_label.setToolTip('Display zoom only · does not change saved notes formatting')
        row2.addWidget(self.notes_zoom_label)

        hint = QLabel(('⌘-click ↗ to follow a page link' if IS_MAC else 'Ctrl-click ↗ to follow a page link'))
        hint.setObjectName('hintLabel')
        hint.setWordWrap(True)
        root.addWidget(hint)

        # This search strip is hidden by default. It sits above the editor,
        # so Ctrl/Command+F never steals vertical room when it isn't needed.
        self.search_strip = QWidget()
        search_row = QHBoxLayout(self.search_strip)
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(5)
        self.find_input = QLineEdit()
        self.find_input.setObjectName('notesFindInput')
        self.find_input.setPlaceholderText('Find in notes…')
        self.find_input.setClearButtonEnabled(True)
        self.find_input.setToolTip(f'Find in notes · {docs_shortcut("find")}; Return for next')
        search_row.addWidget(self.find_input, 1)
        self.find_previous_button = QToolButton()
        self.find_previous_button.setText('↑')
        self.find_previous_button.setToolTip(f'Previous match · {docs_shortcut("find_previous")}')
        search_row.addWidget(self.find_previous_button)
        self.find_next_button = QToolButton()
        self.find_next_button.setText('↓')
        self.find_next_button.setToolTip(f'Next match · {docs_shortcut("find_next")}')
        search_row.addWidget(self.find_next_button)
        self.find_status = QLabel('')
        self.find_status.setObjectName('hintLabel')
        search_row.addWidget(self.find_status)
        search_close = QToolButton()
        search_close.setText('×')
        search_close.setToolTip('Close find bar · Escape')
        search_close.clicked.connect(self.close_find)
        search_row.addWidget(search_close)
        root.addWidget(self.search_strip)
        self.search_strip.hide()

        self.editor = LinkTextEdit()
        self.page_setup = None
        self._last_edit_cursor = None
        self.editor.page_setup_resize_handler = self._apply_frame_margins
        self.editor.list_return_handler = self._after_list_return
        self.editor.docs_key_handler = self.handle_docs_keystroke
        self.editor.table_tab_handler = self.tables.handle_tab
        self.editor.table_tools = self.tables
        self.editor.table_pointer_handler = self.tables.handle_pointer
        self.editor.table_hover_help = (
            'Table: drag a divider to resize · click corner to select all\n'
            f'Insert table: {docs_shortcut("insert_table")}\n'
            f'Row above / below: {docs_shortcut("table_row_before")} / '
            f'{docs_shortcut("table_row_after")}\n'
            f'Column left / right: {docs_shortcut("table_column_before")} / '
            f'{docs_shortcut("table_column_after")}\n'
            f'Delete row: {docs_shortcut("table_delete_row")}\n'
            f'Delete column: {docs_shortcut("table_delete_column")}')
        self.editor.table_context_provider = (
            lambda parent: self.tables.build_menu(
                parent, include_insert=False))
        self.editor.cursorPositionChanged.connect(
            self.editor.viewport().update)
        self.editor.document().setDocumentMargin(20)  # Breathing room for reading.
        self.editor.setAcceptRichText(True)
        self.editor.setPlaceholderText('Write your thoughts, annotations, reading notes and quotations here…')
        # Yomu v0.3.1 hotfix: The document's *default* font must match
        # the editing font. Otherwise Qt falls back to a tiny font when it
        # clears paragraph formatting, regardless of the toolbar setting.
        base_font = QFont(self.defaults.get('font', 'Helvetica'),
                          int(self.defaults.get('font_size', 13)))
        self.editor.document().setDefaultFont(base_font)
        # A visual-only overlay renders zoomed sizes without altering HTML.
        self._view_zoom_overlay = NotesViewZoomHighlighter(self.editor.document())
        self.editor.setFont(base_font)
        self.editor.setFontPointSize(int(self.defaults.get('font_size', 13)))
        self.editor.setFontWeight(QFont.Weight.Bold if self.defaults.get('bold') else QFont.Weight.Normal)
        self.editor.setFontItalic(bool(self.defaults.get('italic')))
        self.editor.setAlignment({'Left': Qt.AlignmentFlag.AlignLeft,
                                  'Centre': Qt.AlignmentFlag.AlignHCenter,
                                  'Right': Qt.AlignmentFlag.AlignRight,
                                  'Justify': Qt.AlignmentFlag.AlignJustify}.get(
                                      self.defaults.get('alignment', 'Left'), Qt.AlignmentFlag.AlignLeft))
        root.addWidget(self.editor, 1)

        self.font_choice.currentFontChanged.connect(self.on_font_changed)
        self.font_size.valueChanged.connect(self.set_font_size_immediately)
        self.heading_choice.currentIndexChanged.connect(self.change_heading)
        self.editor.currentCharFormatChanged.connect(self.update_font_toolbar)
        self.editor.cursorPositionChanged.connect(self._sync_heading_choice)
        self.editor.selectionChanged.connect(self._sync_heading_choice)
        self.editor.textChanged.connect(self.changed.emit)
        self.editor.document().contentsChange.connect(self._remember_edit_from_contents_change)
        self.editor.linkActivated.connect(self.open_link)
        self.find_input.textChanged.connect(self.find_from_start)
        self.find_input.returnPressed.connect(self.find_next)
        self.find_next_button.clicked.connect(self.find_next)
        self.find_previous_button.clicked.connect(self.find_previous)
        self.find_input.installEventFilter(self)
        self.wire_toggles()
        self.setup_shortcuts()

    def _remember_edit_from_contents_change(self, position, removed, added):
        # Only text insertions/deletions update Jump to Edit, not scrolling or resizing.
        if removed or added:
            self._last_edit_cursor = QTextCursor(self.editor.document())
            self._last_edit_cursor.setPosition(min(self.editor.document().characterCount()-1,
                                                   max(0, position+added)))

    def jump_to_edit_position(self):
        """Explicit recovery button when a reflow moved the visible reading line."""
        cursor = self._last_edit_cursor
        if cursor is None or cursor.isNull():
            cursor = self.editor.textCursor()
        self.editor._wheel_animation.stop()
        self.editor.setTextCursor(QTextCursor(cursor))
        self.editor.ensureCursorVisible()
        self.editor.setFocus()

    def set_jump_edit_visible(self, visible: bool):
        self.jump_edit_button.setVisible(bool(visible))

    def _layout_dpi(self) -> float:
        return float(self.editor.logicalDpiY())

    def _apply_frame_margins(self):
        """Set four independent root-frame margins without changing paragraph indents."""
        setup = self.page_setup
        if setup is None:
            return
        document = self.editor.document()
        viewport_width = max(0, self.editor.viewport().width()-8)
        top, bottom, left, right = fitted_margins(setup, self._layout_dpi(), viewport_width)
        frame = document.rootFrame()
        fmt = frame.frameFormat()
        margins = (fmt.topMargin(), fmt.bottomMargin(), fmt.leftMargin(), fmt.rightMargin())
        target = (top, bottom, left, right)
        if all(abs(a-b) < 0.2 for a, b in zip(margins, target)):
            return
        fmt.setTopMargin(top)
        fmt.setBottomMargin(bottom)
        fmt.setLeftMargin(left)
        fmt.setRightMargin(right)
        frame.setFrameFormat(fmt)

    def _is_last_list_item(self, block):
        """Only the final item before an ordinary paragraph gets the normal gap."""
        # Lists inside a table cell should stay compact.
        if QTextCursor(block).currentTable() is not None:
            return False
        next_block = block.next()
        return not next_block.isValid() or next_block.textList() is None

    def _apply_paragraph_defaults(self, old_setup=None):
        """Change inherited defaults without erasing explicit overrides.

        Each QTextBlock has an optional override, measured in points.
        Point values follow the document between operating systems.
        Qt needs pixels for its on-screen layout, so conversion only
        happens at the last moment, using this machine's logical DPI.
        """
        setup = self.page_setup
        if setup is None:
            return
        document = self.editor.document()
        dpi = self._layout_dpi()
        after = pt_to_px(
            setup.after_for_font(self._base_document_point_size()), dpi)
        former = (pt_to_px(old_setup.after_for_font(
            self._base_document_point_size()), dpi)
            if old_setup is not None else None)
        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        try:
            block = document.firstBlock()
            while block.isValid():
                next_block = block.next()
                fmt = block.blockFormat()
                is_list = block.textList() is not None
                # Tables use the same QTextBlock objects as normal
                # paragraphs. Do not put document-level 8 pt gaps
                # inside cells of a borderless layout table.
                in_cell = QTextCursor(block).currentTable() is not None
                expected = (0.0 if in_cell else after if not is_list or
                            self._is_last_list_item(block) else 0.0)
                previous = (0.0 if in_cell else former if not is_list or
                            self._is_last_list_item(block) else 0.0)
                current = fmt.bottomMargin()

                if fmt.hasProperty(_AFTER_PT_OVERRIDE):
                    # 0 pt is meaningful: never replace it with 8 pt.
                    fmt.setBottomMargin(pt_to_px(
                        float(fmt.property(_AFTER_PT_OVERRIDE)), dpi))
                elif (abs(current) < 0.1 or abs(current-after) < 0.1 or
                      (former is not None and abs(current-previous) < 0.1)):
                    fmt.setBottomMargin(expected)

                if fmt.hasProperty(_BEFORE_PT_OVERRIDE):
                    fmt.setTopMargin(pt_to_px(
                        float(fmt.property(_BEFORE_PT_OVERRIDE)), dpi))
                elif in_cell:
                    fmt.setTopMargin(0.0)

                if fmt.hasProperty(_LINE_MULTIPLIER_OVERRIDE):
                    fmt.setLineHeight(
                        float(fmt.property(_LINE_MULTIPLIER_OVERRIDE)) * 100.0,
                        int(QTextBlockFormat.LineHeightTypes.ProportionalHeight.value))
                elif old_setup is None:
                    if fmt.lineHeightType() == int(
                            QTextBlockFormat.LineHeightTypes.SingleHeight.value):
                        fmt.setLineHeight(
                            setup.line_spacing * 100.0,
                            int(QTextBlockFormat.LineHeightTypes.ProportionalHeight.value))
                elif (fmt.lineHeightType() == int(
                        QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
                      and abs(fmt.lineHeight() - old_setup.line_spacing*100.0) < 0.1):
                    fmt.setLineHeight(
                        setup.line_spacing * 100.0,
                        int(QTextBlockFormat.LineHeightTypes.ProportionalHeight.value))

                if is_list:
                    # List markers stay native, aligned to the list grid.
                    fmt.setLeftMargin(pt_to_px(
                        setup.list_first_text_pt-setup.list_step_pt, dpi))
                    fmt.setTextIndent(0.0)
                if fmt != block.blockFormat():
                    cursor.setPosition(block.position())
                    cursor.setBlockFormat(fmt)
                block = next_block
        finally:
            cursor.endEditBlock()

    def _after_list_return(self, positions):
        """Keep a new list item tidy as soon as Return creates it.

        A newly inserted item inherits some formatting from its neighbour.
        In mixed-size documents that can give its bullet an enormous font.
        Native Qt lists own the markers; we only correct block formatting.
        """
        document = self.editor.document()
        for position in positions:
            block = document.findBlock(position)
            if block.isValid() and block.textList() is not None:
                self._normalise_list_block_presentation(block)
        self._refresh_list_neighbour_spacing(positions)

    def _refresh_list_neighbour_spacing(self, positions):
        """Adjust only selected items and their immediate neighbours after a list edit."""
        setup = self.page_setup
        if setup is None:
            return
        doc = self.editor.document()
        after = pt_to_px(setup.after_for_font(self._base_document_point_size()),
                         self._layout_dpi())
        touched = set()
        for position in positions:
            block = doc.findBlock(position)
            if block.isValid():
                for item in (block.previous(), block, block.next()):
                    if item.isValid():
                        touched.add(item.position())
        cursor = QTextCursor(doc)
        for position in sorted(touched):
            block = doc.findBlock(position)
            if not block.isValid() or block.textList() is None:
                continue
            fmt = block.blockFormat()
            target = after if self._is_last_list_item(block) else 0.0
            # A user-chosen 0 pt gap is still an explicit override.
            if (not fmt.hasProperty(_AFTER_PT_OVERRIDE)
                    and (abs(fmt.bottomMargin()) < 0.1
                         or abs(fmt.bottomMargin()-after) < 0.1)):
                if abs(fmt.bottomMargin()-target) >= 0.1:
                    fmt.setBottomMargin(target)
                    cursor.setPosition(position)
                    cursor.setBlockFormat(fmt)

    def restore_page_setup_metadata(self, setup: NotesPageSetup | None,
                                    *, update_frame=True):
        """Restore saved defaults while Qt Undo restores paragraph formats.

        The Undo history already contains each paragraph's old values.
        We must NOT edit those paragraphs again while replaying Undo.
        """
        self.page_setup = setup
        self.editor.list_return_handler = self._after_list_return
        if setup is None:
            # Legacy notebooks used Qt's ordinary 20-pixel margin.
            # Undoing Page Setup must return to that layout too.
            self.editor.document().setDocumentMargin(20.0)
        else:
            self.editor.document().setDocumentMargin(0.0)
            self.editor.document().setIndentWidth(
                pt_to_px(setup.list_step_pt, self._layout_dpi()))
            if update_frame:
                self._apply_frame_margins()

    def set_page_setup(self, setup: NotesPageSetup | None, *, from_load=False):
        """Apply new document defaults as one native Qt Undo level."""
        old = self.page_setup
        self.page_setup = setup
        self.editor.list_return_handler = self._after_list_return
        if setup is None:
            return

        def apply():
            # Keep the root-frame margins and all affected blocks in
            # the SAME edit transaction. One Undo restores both.
            writer = QTextCursor(self.editor.document())
            writer.beginEditBlock()
            try:
                self.editor.document().setDocumentMargin(0.0)
                self.editor.document().setIndentWidth(
                    pt_to_px(setup.list_step_pt, self._layout_dpi()))
                self._apply_frame_margins()
                self._apply_paragraph_defaults(old)
            finally:
                writer.endEditBlock()

        if from_load:
            apply()
        else:
            self._preserve_editor_view(apply)

    def _set_selected_spacing(self, *, before_pt=None, after_pt=None, line_multiplier=None):
        """Update only the caret block or explicitly selected Qt blocks."""
        selected = self.editor.textCursor()
        positions = list(self._target_block_positions(selected))
        document = self.editor.document()
        dpi = self._layout_dpi()
        def mutate():
            writer = QTextCursor(document)
            writer.beginEditBlock()
            try:
                for position in positions:
                    block = document.findBlock(position)
                    if not block.isValid():
                        continue
                    fmt = block.blockFormat()
                    if before_pt is not None:
                        fmt.setProperty(_BEFORE_PT_OVERRIDE, float(before_pt))
                        fmt.setTopMargin(pt_to_px(before_pt, dpi))
                    if after_pt is not None:
                        fmt.setProperty(_AFTER_PT_OVERRIDE, float(after_pt))
                        fmt.setBottomMargin(pt_to_px(after_pt, dpi))
                    if line_multiplier is not None:
                        fmt.setProperty(_LINE_MULTIPLIER_OVERRIDE,
                                        float(line_multiplier))
                        fmt.setLineHeight(float(line_multiplier)*100.0,
                                          int(QTextBlockFormat.LineHeightTypes.ProportionalHeight.value))
                    writer.setPosition(position)
                    writer.setBlockFormat(fmt)
            finally:
                writer.endEditBlock()
            self.editor.setTextCursor(selected)
        self._preserve_editor_view(mutate)
        self.editor.setFocus()

    def set_selected_paragraph_spacing(self, **values):
        self._set_selected_spacing(**values)

    def reset_selected_spacing(self):
        """Restore inheritance, including for an explicit 0 pt gap.

        Resetting removes each per-paragraph override property rather
        than writing a new override equal to today's default value.
        """
        setup = self.page_setup or NotesPageSetup()
        selected = QTextCursor(self.editor.textCursor())
        positions = list(self._target_block_positions(selected))
        document = self.editor.document()
        dpi = self._layout_dpi()
        after = pt_to_px(setup.after_for_font(
            self._base_document_point_size()), dpi)

        def mutate():
            writer = QTextCursor(document)
            writer.beginEditBlock()
            try:
                for position in positions:
                    block = document.findBlock(position)
                    if not block.isValid():
                        continue
                    fmt = block.blockFormat()
                    for prop in _SPACING_PROPERTIES.values():
                        fmt.clearProperty(prop)
                    fmt.setTopMargin(0.0)
                    in_cell = QTextCursor(block).currentTable() is not None
                    fmt.setBottomMargin(
                        after if not in_cell and (
                            block.textList() is None or
                            self._is_last_list_item(block)) else 0.0)
                    fmt.setLineHeight(
                        setup.line_spacing * 100.0,
                        int(QTextBlockFormat.LineHeightTypes.ProportionalHeight.value))
                    writer.setPosition(position)
                    writer.setBlockFormat(fmt)
            finally:
                writer.endEditBlock()
            self.editor.setTextCursor(selected)

        self._preserve_editor_view(mutate)
        self.editor.setFocus()

    def show_paragraph_spacing(self):
        block = self.editor.textCursor().block()
        fmt = block.blockFormat()
        dpi = self._layout_dpi()
        setup = self.page_setup or NotesPageSetup()
        line = (fmt.lineHeight()/100.0 if fmt.lineHeightType() ==
                int(QTextBlockFormat.LineHeightTypes.ProportionalHeight.value) else setup.line_spacing)
        dialog = ParagraphSpacingDialog(fmt.topMargin()*72.0/dpi,
                                        fmt.bottomMargin()*72.0/dpi, line, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._set_selected_spacing(before_pt=dialog.before.value(),
                                       after_pt=dialog.after.value(),
                                       line_multiplier=dialog.line.value())

    @staticmethod
    def _toggle_action(toolbar: WrapBar, title: str, tooltip: str, kind: str) -> QAction:
        action = toolbar.addAction(title)
        action.setCheckable(True)
        action.setToolTip(tooltip)
        # Connections made after editor is constructed below by the parent constructor.
        action.setProperty('formatKind', kind)
        # Editing shortcuts are owned by the QTextEdit widget below, rather
        # than the toolbar/window: hidden project tabs must not steal them.
        return action

    def wire_toggles(self):
        for action in [self.bold_action, self.italic_action,
                       self.underline_action, self.strike_action]:
            action.toggled.connect(lambda checked, k=action.property('formatKind'): self.toggle_format(k, checked))

    def set_html(self, html: str):
        # Qt exports ordinary paragraph CSS but not custom user
        # properties. A tiny metadata comment accompanies our HTML.
        html, saved_overrides = split_spacing_metadata(html or '')
        self.editor.blockSignals(True)
        try:
            if html:
                self.editor.setHtml(html)
            else:
                self.editor.setPlainText('')
                self.editor.setCurrentFont(QFont(self.defaults.get('font', 'Helvetica'),
                                                 int(self.defaults.get('font_size', 13))))
                self.editor.setFontPointSize(int(self.defaults.get('font_size', 13)))
                self.editor.setFontWeight(QFont.Weight.Bold if self.defaults.get('bold') else QFont.Weight.Normal)
                self.editor.setFontItalic(bool(self.defaults.get('italic')))
                self.editor.setAlignment({'Left': Qt.AlignmentFlag.AlignLeft,
                                          'Centre': Qt.AlignmentFlag.AlignHCenter,
                                          'Right': Qt.AlignmentFlag.AlignRight,
                                          'Justify': Qt.AlignmentFlag.AlignJustify}.get(
                                              self.defaults.get('alignment', 'Left'), Qt.AlignmentFlag.AlignLeft))
            # Restore point-based overrides before the project attaches
            # its Undo history. Each block remains a native Qt paragraph.
            document = self.editor.document()
            dpi = self._layout_dpi()
            writer = QTextCursor(document)
            writer.beginEditBlock()
            try:
                for number, values in saved_overrides.items():
                    block = document.findBlockByNumber(number)
                    if not block.isValid():
                        continue
                    fmt = block.blockFormat()
                    for key, value in values.items():
                        prop = _SPACING_PROPERTIES.get(key)
                        if prop is None:
                            continue
                        fmt.setProperty(prop, value)
                        if key == 'before_pt':
                            fmt.setTopMargin(pt_to_px(value, dpi))
                        elif key == 'after_pt':
                            fmt.setBottomMargin(pt_to_px(value, dpi))
                        elif key == 'line':
                            fmt.setLineHeight(
                                value * 100.0,
                                int(QTextBlockFormat.LineHeightTypes.ProportionalHeight.value))
                    writer.setPosition(block.position())
                    writer.setBlockFormat(fmt)
            finally:
                writer.endEditBlock()
        finally:
            self.editor.blockSignals(False)
        # Loading notes is not a user edit. Otherwise the jump-to-edit
        # button incorrectly points at the end of a reopened document.
        self._last_edit_cursor = None
        self._sync_heading_choice()

    def html(self) -> str:
        # Serialize explicit overrides in typographic POINTS.
        # Qt's normal HTML representation uses display pixels,
        # which can differ across Windows and macOS displays.
        overrides = {}
        block = self.editor.document().firstBlock()
        while block.isValid():
            fmt = block.blockFormat()
            values = {
                name: float(fmt.property(prop))
                for name, prop in _SPACING_PROPERTIES.items()
                if fmt.hasProperty(prop)
            }
            if values:
                overrides[block.blockNumber()] = values
            block = block.next()
        return add_spacing_metadata(self.editor.toHtml(), overrides)

    def toggle_format(self, kind: str, checked: bool):
        fmt = QTextCharFormat()
        if kind == 'bold':
            fmt.setFontWeight(QFont.Weight.Bold if checked else QFont.Weight.Normal)
        elif kind == 'italic':
            fmt.setFontItalic(checked)
        elif kind == 'underline':
            fmt.setFontUnderline(checked)
        elif kind == 'strike':
            fmt.setFontStrikeOut(checked)
        self.apply_format(fmt)

    def apply_format(self, fmt: QTextCharFormat):
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        self.editor.mergeCurrentCharFormat(fmt)
        self.editor.setFocus()

    def on_font_changed(self, font: QFont):
        fmt = QTextCharFormat()
        fmt.setFontFamily(font.family())
        self.apply_format(fmt)

    def _selected_first_size(self) -> float:
        """Use the first *selected* glyph, never the format after the selection.

        A QTextEdit currentFont() at the trailing edge can belong to the
        adjacent run. This is what made repeated A-/A+ bounce or get stuck.
        """
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            probe = QTextCursor(self.editor.document())
            probe.setPosition(min(cursor.selectionStart()+1, cursor.selectionEnd()))
            fmt = probe.charFormat()
            size = fmt.fontPointSize()
            if size <= 0 and fmt.hasProperty(QTextFormat.Property.FontPixelSize):
                size = float(fmt.property(QTextFormat.Property.FontPixelSize)) * 72.0 / 96.0
            if size > 0:
                return float(size)
        # A paragraph can LOOK blank while containing whitespace or invisible
        # characters pasted from a PDF/website. Those need the same stable
        # stored-size baseline as a genuinely empty paragraph.
        size = (cursor.blockCharFormat().fontPointSize()
                if _is_visually_blank_paragraph(cursor.block().text()) else 0)
        if size <= 0:
            size = self.editor.currentCharFormat().fontPointSize()
        if size <= 0:
            size = self.editor.currentFont().pointSizeF()
        if size <= 0:
            size = float(self.font_size.value())
        return max(7.0, size)

    def update_font_toolbar(self, fmt: QTextCharFormat):
        font = self.editor.currentFont()
        with QSignalBlocker(self.font_choice):
            self.font_choice.setCurrentFont(font)
        with QSignalBlocker(self.font_size):
            size = self._selected_first_size()
            self.font_size.setValue(round(size))
        text_colour = fmt.foreground().color()
        if text_colour.isValid():
            self.text_colour_button.set_colour(text_colour)
        bg_colour = fmt.background().color()
        if bg_colour.isValid() and fmt.hasProperty(QTextFormat.Property.BackgroundBrush):
            self.text_highlight_button.set_colour(bg_colour)
        for action, checked in [
            (self.bold_action, fmt.fontWeight() >= QFont.Weight.Bold),
            (self.italic_action, fmt.fontItalic()),
            (self.underline_action, fmt.fontUnderline()),
            (self.strike_action, fmt.fontStrikeOut()),
        ]:
            with QSignalBlocker(action):
                action.setChecked(checked)

    def _sync_heading_choice(self):
        """Display the heading level of the caret or current selection.

        QTextBlock stores the actual heading level.
        We inspect only the selected blocks, never nearby text styles.
        A mixed selection says 'Mixed' instead of falsely showing H1.
        """
        cursor = self.editor.textCursor()
        positions = self._target_block_positions(cursor)
        document = self.editor.document()
        levels = {
            max(0, min(6, int(document.findBlock(position)
                               .blockFormat().headingLevel())))
            for position in positions
            if document.findBlock(position).isValid()
        }
        target = (levels.pop() if len(levels) == 1
                  else 7 if len(levels) > 1 else 0)
        with QSignalBlocker(self.heading_choice):
            self.heading_choice.setCurrentIndex(target)

    def change_heading(self, index: int):
        """Apply a heading to every selected paragraph, never just one.

        A paragraph is a QTextBlock: an actual structural piece of the
        Qt document. A wrapped visual line is NOT another paragraph.
        We first collect the exact blocks touched by the selection.

        One edit block gives the whole change a single Undo entry.
        """
        sizes = [int(self.defaults.get('font_size', 13)),
                 24, 19, 16, 14, 13, 12]
        if index < 0 or index > 6:
            return
        original = QTextCursor(self.editor.textCursor())
        positions = list(self._target_block_positions(original))
        document = self.editor.document()

        def apply_heading():
            group = QTextCursor(document)
            group.beginEditBlock()
            try:
                for position in positions:
                    block = document.findBlock(position)
                    if not block.isValid():
                        continue

                    # Set a true paragraph heading level, not a prefix.
                    cursor = QTextCursor(document)
                    cursor.setPosition(block.position())
                    block_format = cursor.blockFormat()
                    block_format.setHeadingLevel(index)
                    cursor.setBlockFormat(block_format)

                    # Text styling is applied to this specific block.
                    # The final -1 excludes its paragraph-break marker.
                    text_format = QTextCharFormat()
                    text_format.setFontPointSize(float(sizes[index]))
                    text_format.setFontWeight(
                        QFont.Weight.Normal if index == 0
                        else QFont.Weight.Bold)
                    if block.length() > 1:
                        cursor.setPosition(block.position())
                        cursor.setPosition(
                            block.position() + block.length() - 1,
                            QTextCursor.MoveMode.KeepAnchor)
                        cursor.mergeCharFormat(text_format)
                    else:
                        # An empty heading still needs a typing font.
                        cursor.setBlockCharFormat(text_format)
            finally:
                group.endEditBlock()
            self.editor.setTextCursor(original)
            self.editor.setFocus()

        self._preserve_editor_view(apply_heading)
        self._sync_heading_choice()

    def _preserve_editor_view(self, callback):
        # Capture and restore scroll/caret so indenting and list edits do not jump the view.
        self.editor.preserve_view_state(callback)

    def _base_document_point_size(self) -> float:
        font = self.editor.document().defaultFont()
        size = font.pointSizeF()
        return size if size > 0 else float(self.font_size.value())

    def _normalise_list_block_presentation(self, block):
        # Keep list markers tied to a stable base block format instead of inheriting huge item text.
        point = QTextCursor(self.editor.document())
        point.setPosition(block.position())
        block_fmt = point.blockFormat()
        changed = False
        if block_fmt.indent():
            block_fmt.setIndent(0)
            changed = True
        # QTextList draws its marker beside the FIRST line of its block.
        # A leftover HTML text-indent / margin can push that line away.
        # Remove only horizontal offsets, not paragraph spacing.
        if abs(block_fmt.textIndent()) > 0.01:
            block_fmt.setTextIndent(0.0)
            changed = True
        if abs(block_fmt.leftMargin()) > 0.01:
            block_fmt.setLeftMargin(0.0)
            changed = True
        if abs(block_fmt.rightMargin()) > 0.01:
            block_fmt.setRightMargin(0.0)
            changed = True
        # Paragraph spacing is independent of marker sizing and must survive edits.
        if changed:
            point.setBlockFormat(block_fmt)
        char_fmt = point.blockCharFormat()
        base = self._base_document_point_size()
        current = char_fmt.fontPointSize()
        if current <= 0 or abs(current - base) > 0.01:
            char_fmt.setFontPointSize(base)
            point.setBlockCharFormat(char_fmt)

    @staticmethod
    def _target_block_positions(cursor):
        """Return only the paragraphs actually touched by the caret/selection.

        The end of a selection is exclusive: if it stops at the start of
        the next paragraph, that next paragraph must NOT be modified.
        Positions, not visual/wrapped line numbers, identify Qt blocks.
        """
        document = cursor.document()
        first = document.findBlock(cursor.selectionStart())
        if not first.isValid():
            return []
        if not cursor.hasSelection():
            return [first.position()]
        last = document.findBlock(max(cursor.selectionStart(), cursor.selectionEnd() - 1))
        positions = []
        block = first
        while block.isValid() and block.position() <= last.position():
            positions.append(block.position())
            block = block.next()
        return positions

    @staticmethod
    def _list_kind(style):
        """Distinguish ordered from bullet Qt list objects, without text inference."""
        return ('ordered' if style in (
            QTextListFormat.Style.ListDecimal,
            QTextListFormat.Style.ListLowerAlpha,
            QTextListFormat.Style.ListUpperAlpha,
            QTextListFormat.Style.ListLowerRoman,
            QTextListFormat.Style.ListUpperRoman,
        ) else 'bullet')

    @staticmethod
    def _style_for_level(kind, level):
        """Choose a REAL Qt marker appropriate to the nesting depth.

        These are not bullet characters inserted into the text.
        Qt positions each marker alongside the line it belongs to.
        """
        if kind == 'ordered':
            styles = (QTextListFormat.Style.ListDecimal,
                      QTextListFormat.Style.ListLowerAlpha,
                      QTextListFormat.Style.ListLowerRoman)
        else:
            styles = (QTextListFormat.Style.ListDisc,
                      QTextListFormat.Style.ListCircle,
                      QTextListFormat.Style.ListSquare)
        return styles[(max(1, int(level))-1) % len(styles)]

    @staticmethod
    def _has_previous_list_parent(block):
        """Find the preceding list parent without treating blanks as items.

        Ordered lists can continue numbering over blank paragraphs, so allow
        indenting the later ordered item under the preceding ordered item.
        Bullet-list blanks remain true group boundaries: they must not create
        a nesting parent. Ordinary text never counts as a parent.
        """
        previous = block.previous()
        current_list = block.textList()
        if (current_list is not None
                and NotesEditor._list_kind(current_list.format().style()) == 'ordered'):
            while previous.isValid() and _is_visually_blank_paragraph(previous.text()):
                previous = previous.previous()
        return (previous.isValid()
                and previous.textList() is not None
                and not _is_visually_blank_paragraph(previous.text()))

    def _peer_list(self, block, target_indent, style):
        """Find a *real* neighbouring QTextList at the requested depth/kind.

        Only QTextBlock.textList() determines membership. Inspecting nearby
        blocks here lets us *reuse* a native list for numbering continuity;
        it never classifies a paragraph as a list item by appearance.
        An ordinary blank paragraph can bridge ordered numbering, but cuts
        bullet-list groups into separate lists.
        """
        ordered = self._list_kind(style) == 'ordered'
        for backwards in (True, False):
            neighbour = block.previous() if backwards else block.next()
            hops = 0
            while neighbour.isValid() and hops < 120:
                hops += 1
                peer = neighbour.textList()
                if peer is None:
                    if ordered and _is_visually_blank_paragraph(neighbour.text()):
                        neighbour = neighbour.previous() if backwards else neighbour.next()
                        continue
                    break
                peer_format = peer.format()
                level = peer_format.indent()
                if level == target_indent:
                    if peer_format.style() == style:
                        return peer
                    break  # A different list type is an explicit boundary.
                if level < target_indent:
                    break  # Do not search across a parent/sibling list.
                # A deeper nested list can separate siblings of one Qt list.
                neighbour = neighbour.previous() if backwards else neighbour.next()
        return None

    def _put_block_in_list(self, block, target_indent, style):
        """Move one actual QTextBlock to one native list, keeping Qt markers."""
        document = self.editor.document()
        point = QTextCursor(document)
        point.setPosition(block.position())
        # Paragraph indent is separate from Qt list indent. Never stack them:
        # doing so pushes bullets/numbers away from their own text.
        if block.blockFormat().indent():
            modifier = QTextBlockFormat()
            modifier.setIndent(0)
            modifier.setTextIndent(0.0)
            point.mergeBlockFormat(modifier)
        self._normalise_list_block_presentation(block)
        peer = self._peer_list(block, target_indent, style)
        if peer is not None:
            peer.add(block)
        else:
            fmt = QTextListFormat()
            fmt.setStyle(style)
            fmt.setIndent(target_indent)  # A positive first level keeps markers in view.
            point.createList(fmt)  # Single block; never convert a selected range.

    def _change_list_item_level(self, block, change):
        """Sink/lift ONLY this explicit Qt list item; return True if changed."""
        actual_list = block.textList()
        if actual_list is None:
            return False
        old = actual_list.format()
        level = max(1, old.indent())
        if change > 0:
            # A first item in a NEW sublist has itemNumber zero.
            # That does not mean it cannot be nested further.
            if level >= 12 or not self._has_previous_list_parent(block):
                return False
            target = level + 1
        else:
            target = level - 1
            if target == 0:
                # Outdenting a top-level item exits its list; leave its
                # neighbours and their native numbering completely alone.
                actual_list.remove(block)
                point = QTextCursor(self.editor.document())
                point.setPosition(block.position())
                modifier = QTextBlockFormat()
                modifier.setIndent(0)
                modifier.setTextIndent(0.0)
                point.mergeBlockFormat(modifier)
                return True
        style = self._style_for_level(self._list_kind(old.style()), target)
        self._put_block_in_list(block, target, style)
        return True

    def indent(self, change: int):
        """Ctrl/Cmd+[ or ] affects ONLY the explicit caret/selection blocks.

        Qt QTextList remains the structural owner of each list item and marker.
        Never call QTextList.setFormat() to indent just one member: it changes
        the formatting of EVERY item in that list (the original bug).
        """
        selection = self.editor.textCursor()
        positions = list(self._target_block_positions(selection))
        document = self.editor.document()

        def apply_indent():
            transaction = QTextCursor(document)
            transaction.beginEditBlock()  # One Undo step even for a multi-item selection.
            try:
                for position in positions:
                    block = document.findBlock(position)
                    if not block.isValid():
                        continue
                    # Selected blank paragraphs are separators, not implied items.
                    if selection.hasSelection() and _is_visually_blank_paragraph(block.text()):
                        continue
                    if block.textList() is not None:
                        self._change_list_item_level(block, change)
                        self._normalise_list_block_presentation(block)
                    else:
                        # Defined fallback: normal paragraphs get paragraph-only
                        # indent, never their previous/next list item's indent.
                        current = block.blockFormat().indent()
                        target = max(0, min(12, current + (1 if change > 0 else -1)))
                        if current != target:
                            point = QTextCursor(document)
                            point.setPosition(block.position())
                            modifier = QTextBlockFormat()
                            modifier.setIndent(target)
                            point.mergeBlockFormat(modifier)
                self._refresh_list_neighbour_spacing(positions)
            finally:
                transaction.endEditBlock()
            # No text was inserted/removed; preserve the caret or exact selection.
            self.editor.setTextCursor(selection)
            self.editor.setFocus()

        self._preserve_editor_view(apply_indent)

    def insert_horizontal_line(self):
        """An ordinary HTML <hr>, saved in project notes and undoable by Qt."""
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        cursor.insertHtml('<hr />')
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def set_font_size_immediately(self, points: int):
        """Apply font size using native QTextEdit formatting and undo support.

        A previous experiment forced QTextBlockFormat.FixedHeight during an
        unclosed edit block, crashing on PySide6's integer-only API and
        damaging Undo/Redo until restart. Never override paragraph line
        height just to alter the insertion font: let Qt lay out real text.
        Empty-block char formatting is stored without inserting junk glyphs.
        """
        points = max(7, min(120, int(points)))
        editor = self.editor
        cursor = editor.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontPointSize(float(points))
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
            editor.setTextCursor(cursor)
        else:
            if _is_visually_blank_paragraph(cursor.block().text()):
                # A line containing only whitespace/invisible spans is just as
                # visually blank as an empty block. Previously those spans kept
                # their OLD font metrics, so resizing appeared inconsistent.
                # Keep all three formats (separator, any actual run, paragraph)
                # in one native undoable edit without inserting filler text.
                cursor.beginEditBlock()
                try:
                    block_char = QTextCharFormat(cursor.blockCharFormat())
                    block_char.setFontPointSize(float(points))
                    cursor.setBlockCharFormat(block_char)
                    block = cursor.block()
                    if block.length() > 1:
                        # Include *only* existing characters, never the final
                        # paragraph separator or the next paragraph's format.
                        run_cursor = QTextCursor(editor.document())
                        run_cursor.setPosition(block.position())
                        run_cursor.setPosition(block.position() + block.length() - 1,
                                               QTextCursor.MoveMode.KeepAnchor)
                        run_cursor.mergeCharFormat(fmt)
                    # A minimum (not fixed) line height gives truly blank
                    # paragraphs real geometry and can both grow and shrink.
                    font = QFont(editor.currentFont())
                    font.setPointSizeF(float(points))
                    minimum = max(1.0, QFontMetricsF(font).lineSpacing())
                    block_fmt = cursor.blockFormat()
                    block_fmt.setLineHeight(
                        minimum,
                        int(QTextBlockFormat.LineHeightTypes.MinimumHeight.value))
                    cursor.setBlockFormat(block_fmt)
                finally:
                    cursor.endEditBlock()
                editor.document().markContentsDirty(
                    cursor.block().position(), max(1, cursor.block().length()))
            # Setting the cursor refreshes Qt's insertion format; apply the
            # chosen typing size only AFTER restoring the cursor.
            editor.setTextCursor(cursor)
            editor.mergeCurrentCharFormat(fmt)

        with QSignalBlocker(self.font_size):
            self.font_size.setValue(points)
        editor.ensureCursorVisible()
        editor.viewport().update()

    def count_fixed_height_paragraphs(self) -> int:
        """Count paragraphs affected by a fixed line-height style."""
        doc = self.editor.document()
        block = doc.firstBlock()
        count = 0
        while block.isValid():
            if block.blockFormat().lineHeightType() == QTextBlockFormat.LineHeightTypes.FixedHeight.value:
                count += 1
            block = block.next()
        return count

    def repair_fixed_height_paragraphs(self) -> int:
        """Restore natural line heights as one undoable formatting edit.

        This specifically repairs paragraph styles left by the faulty 0.4.4b
        empty-line font size code, including files already saved with them.
        It is opt-in so we never silently change deliberate imported styles.
        """
        doc = self.editor.document()
        before = self.editor.textCursor()
        scroll = self.editor.verticalScrollBar().value()
        changed = 0
        group = QTextCursor(doc)
        group.beginEditBlock()
        try:
            block = doc.firstBlock()
            while block.isValid():
                following = block.next()
                if block.blockFormat().lineHeightType() == QTextBlockFormat.LineHeightTypes.FixedHeight.value:
                    # The repair remains a single native Undo operation.
                    group.setPosition(block.position())
                    fmt = group.blockFormat()
                    # PySide6 requires an int, NOT a LineHeightTypes enum.
                    fmt.setLineHeight(
                        0.0, int(QTextBlockFormat.LineHeightTypes.SingleHeight.value))
                    group.setBlockFormat(fmt)
                    changed += 1
                block = following
        finally:
            group.endEditBlock()
        self.editor.setTextCursor(before)
        self.editor.verticalScrollBar().setValue(scroll)
        return changed

    def change_font_size(self, step: int):
        """Adjust real selected runs by one step, without re-reading a stale toolbar.

        Each selected fragment retains its relative size. The whole adjustment
        is one native QTextDocument edit block, preserving rich formatting and
        the existing undo/redo mechanism. It changes NO paragraph line height.
        """
        step = 1 if step > 0 else -1
        editor = self.editor
        original = editor.textCursor()
        if not original.hasSelection():
            new_size = max(7, min(120, round(self._selected_first_size() + step)))
            self.set_font_size_immediately(new_size)
            editor.setFocus()
            return
        doc = editor.document()
        start, end = original.selectionStart(), original.selectionEnd()
        # Collect fragments *before* making an edit. Traversing fragments while
        # merging their char formats would invalidate the iterator.
        changes = []
        block = doc.findBlock(start)
        while block.isValid() and block.position() < end:
            for fragment in block:
                run = fragment.fragment()
                if not run.isValid():
                    continue
                lo = max(start, run.position())
                hi = min(end, run.position() + run.length())
                if lo >= hi:
                    continue
                run_format = run.charFormat()
                previous = run_format.fontPointSize()
                if previous <= 0 and run_format.hasProperty(QTextFormat.Property.FontPixelSize):
                    previous = float(run_format.property(QTextFormat.Property.FontPixelSize)) * 72.0 / 96.0
                if previous <= 0:
                    previous = (block.charFormat().fontPointSize()
                                or doc.defaultFont().pointSizeF()
                                or self.defaults.get('font_size', 13))
                following = max(7, min(120, round(previous + step)))
                if following != round(previous):
                    changes.append((lo, hi, following))
            block = block.next()
        if changes:
            group = QTextCursor(doc)
            group.beginEditBlock()
            try:
                for lo, hi, size in changes:
                    part = QTextCursor(doc)
                    part.setPosition(lo)
                    part.setPosition(hi, QTextCursor.MoveMode.KeepAnchor)
                    fmt = QTextCharFormat()
                    fmt.setFontPointSize(float(size))
                    part.mergeCharFormat(fmt)
            finally:
                group.endEditBlock()
            editor.setTextCursor(original)  # keep the user's exact selection
        with QSignalBlocker(self.font_size):
            self.font_size.setValue(max(7, min(120, round(self._selected_first_size()))))
        editor.setFocus()

    def clear_formatting(self):
        """Remove explicit character colours so the current theme wins.

        Dark and light themes use different paper and ink colours.
        Writing a permanent dark blue into the document makes text
        unreadable when a dark theme is selected later.

        Unlike mergeCharFormat(), setCharFormat() removes the old
        foreground/highlight properties from selected characters.
        """
        fmt = QTextCharFormat()
        fmt.setFontFamily(self.defaults.get('font', 'Helvetica'))
        fmt.setFontPointSize(int(self.defaults.get('font_size', 13)))
        fmt.setFontWeight(QFont.Weight.Normal)
        fmt.setFontItalic(False)
        fmt.setFontUnderline(False)
        fmt.setFontStrikeOut(False)
        fmt.setAnchor(False)
        fmt.setAnchorHref('')
        editor = self.editor
        cursor = editor.textCursor()
        if cursor.hasSelection():
            cursor.setCharFormat(fmt)
            editor.setTextCursor(cursor)
        else:
            editor.setCurrentCharFormat(fmt)
        editor.setFocus()

    def handle_docs_keystroke(self, event) -> bool:
        """Recognise Google Docs chords independent of punctuation key layout.

        On many Windows keyboards the shifted key is delivered as '>' instead
        of '.'. Similar translations occur for comma, brackets and 7/8.
        We handle these while the editor has focus, before QTextEdit consumes
        them, with other shortcuts registered normally in setup_shortcuts().
        """
        mods = event.modifiers()
        primary = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        key = event.key()
        # Catch the physical plus/minus keys before the editor inserts them.
        # Plus is often Shift+Equals on US/UK keyboards; keypad plus is Key_Plus.
        # Qt maps this logical Control modifier to Command on macOS.
        if primary and not alt:
            if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.zoom_notes(+1)
                return True
            if key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
                self.zoom_notes(-1)
                return True
            if key == Qt.Key.Key_0 and not shift:
                self.reset_notes_zoom()
                return True
        if primary and shift and not alt:
            if key in (Qt.Key.Key_Period, Qt.Key.Key_Greater):
                self.change_font_size(+1)
                return True
            if key in (Qt.Key.Key_Comma, Qt.Key.Key_Less):
                self.change_font_size(-1)
                return True
            if key in (Qt.Key.Key_7, Qt.Key.Key_Ampersand):
                self.make_list(True)
                return True
            if key in (Qt.Key.Key_8, Qt.Key.Key_Asterisk):
                self.make_list(False)
                return True
        if primary and not shift and not alt:
            if key in (Qt.Key.Key_BracketRight, Qt.Key.Key_BraceRight):
                self.indent(+1)
                return True
            if key in (Qt.Key.Key_BracketLeft, Qt.Key.Key_BraceLeft):
                self.indent(-1)
                return True
        return False

    def setup_shortcuts(self):
        """Install editor-local Google Docs combinations with platform-aware keys.

        QKeySequence('Ctrl+…') is translated to Command on macOS by Qt.
        Importantly, we don't use widget-global shortcuts: another project
        tab can't intercept keys while editing the currently active document.
        """
        bindings = {
            'Ctrl+B': lambda: self.bold_action.trigger(),
            'Ctrl+I': lambda: self.italic_action.trigger(),
            'Ctrl+U': lambda: self.underline_action.trigger(),
            'Ctrl+Shift+V': self.paste_plain_text,
            # Only the focused notes editor gets these table keys.
            # Page navigation uses Ctrl+Alt+arrows WITHOUT Shift.
            'Ctrl+Shift+T': self.tables.insert_table,
            'Ctrl+Alt+Shift+Up': self.tables.add_row_above,
            'Ctrl+Alt+Shift+Down': self.tables.add_row_below,
            'Ctrl+Alt+Shift+Left': self.tables.add_column_left,
            'Ctrl+Alt+Shift+Right': self.tables.add_column_right,
            # Delete only the current table row/column. Qt maps
            # Ctrl to Command on macOS automatically.
            'Ctrl+Alt+Shift+R': self.tables.remove_row,
            'Ctrl+Alt+Shift+C': self.tables.remove_column,
            'Ctrl+Shift+L': lambda: self.editor.setAlignment(Qt.AlignmentFlag.AlignLeft),
            'Ctrl+Shift+E': lambda: self.editor.setAlignment(Qt.AlignmentFlag.AlignHCenter),
            'Ctrl+Shift+R': lambda: self.editor.setAlignment(Qt.AlignmentFlag.AlignRight),
            'Ctrl+Shift+J': lambda: self.editor.setAlignment(Qt.AlignmentFlag.AlignJustify),
            ('Ctrl+Shift+X' if IS_MAC else 'Alt+Shift+5'):
                lambda: self.strike_action.trigger(),
            'Ctrl+Alt+0': lambda: self.heading_choice.setCurrentIndex(0),
            'Ctrl+Alt+1': lambda: self.heading_choice.setCurrentIndex(1),
            'Ctrl+Alt+2': lambda: self.heading_choice.setCurrentIndex(2),
            'Ctrl+Alt+3': lambda: self.heading_choice.setCurrentIndex(3),
            'Ctrl+Alt+4': lambda: self.heading_choice.setCurrentIndex(4),
            'Ctrl+Alt+5': lambda: self.heading_choice.setCurrentIndex(5),
            'Ctrl+Alt+6': lambda: self.heading_choice.setCurrentIndex(6),
            'Ctrl+\\': self.clear_formatting,
            # Yomu's long-standing shortcut creates an internal PAGE link.
            # Website hyperlinks remain available through Ctrl/Cmd+Alt/Option+K
            # and the optional toolbar button / More menu.
            'Ctrl+K': self.pageLinkRequested.emit,
            'Ctrl+Alt+K': self.insert_web_link,
            # The notes view handles Ctrl/Command +/-/0 in keyPressEvent
            # for reliable shifted-keyboard and keypad recognition.
        }
        for keys, callback in bindings.items():
            shortcut = QShortcut(QKeySequence(keys), self.editor)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def _apply_notes_zoom(self, target_step: int):
        """Zoom the notes around the active line, not the top of the document.

        Rehighlighting changes rich-text line heights and reflows paragraphs.
        Leaving the scrollbar at its previous absolute value can jump to a
        different passage. Keep the editing caret at its current screen Y; if
        it isn't visible (because the reader scrolled elsewhere), preserve the
        first visible line instead.

        The anchor is a QTextCursor pointing at existing text. Nothing is
        inserted into the document or added to its Undo/Redo stack. Each new
        zoom invalidates any pending alignment from the previous zoom.
        """
        target_step = max(-4, min(8, int(target_step)))
        if target_step == self._notes_zoom_points:
            return
        editor = self.editor
        viewport = editor.viewport()
        scrollbar = editor.verticalScrollBar()
        # Stop any in-flight mouse-wheel easing: otherwise it can immediately
        # overwrite our new position after the layout has finished updating.
        editor._wheel_animation.stop()
        caret = editor.textCursor()
        caret_rect = editor.cursorRect(caret)
        caret_is_visible = (0 <= caret_rect.center().y() < viewport.height()
                            and 0 <= caret_rect.center().x() < viewport.width())
        anchor = (caret if caret_is_visible else
                  editor.cursorForPosition(QPoint(12, min(18, max(0, viewport.height()-1)))))
        initial_y = editor.cursorRect(anchor).top()
        self._zoom_anchor_token += 1
        token = self._zoom_anchor_token

        self._notes_zoom_points = target_step
        scale = 1.12 ** target_step
        self._view_zoom_overlay.set_view_scale(scale)
        self.notes_zoom_label.setText(f'Notes · {scale * 100:.0f}%')

        def align_after_reflow():
            # Qt may finish laying out the QTextDocument on the next event
            # turn. Use the same text anchor and cancel obsolete callbacks.
            if token != self._zoom_anchor_token:
                return
            new_y = editor.cursorRect(anchor).top()
            scrollbar.setValue(scrollbar.value() + round(new_y - initial_y))
            # For a very large zoom, clamping may prevent an exact Y match.
            # In that case ensure the editing caret is not left off-screen.
            if caret_is_visible:
                rect = editor.cursorRect(caret)
                if rect.top() < 0 or rect.bottom() > viewport.height():
                    editor.ensureCursorVisible()
            viewport.update()

        QTimer.singleShot(0, align_after_reflow)

    def zoom_notes(self, step: int):
        """Change *display* magnification without changing saved note fonts."""
        self._apply_notes_zoom(self._notes_zoom_points + step)

    def reset_notes_zoom(self):
        """Return to 100% while retaining the current reading/caret line."""
        self._apply_notes_zoom(0)

    def open_find(self):
        """Reveal search with the current selection prefilled when useful."""
        selected = self.editor.textCursor().selectedText().strip()
        self.search_strip.show()
        if selected and len(selected) <= 120 and '\u2029' not in selected:
            self.find_input.setText(selected)
        self.find_input.setFocus()
        self.find_input.selectAll()

    def close_find(self):
        """Dismiss the search UI without changing the underlying note."""
        self.search_strip.hide()
        self.editor.setFocus()

    def eventFilter(self, watched, event):
        """Let Escape close find without accidentally editing the document."""
        if watched is self.find_input and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.close_find()
                return True
        return super().eventFilter(watched, event)

    def find_from_start(self, value: str):
        """Find the first match as the user types, without modifying notes."""
        self.find_status.setText('')
        if not value:
            return
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.editor.setTextCursor(cursor)
        self._find_in_notes(backwards=False, wrap=False)

    def _find_in_notes(self, backwards=False, wrap=True):
        """Navigate text matches, wrapping once at the document boundary."""
        needle = self.find_input.text()
        if not needle:
            return
        flags = (QTextDocument.FindFlag.FindBackward if backwards
                 else QTextDocument.FindFlag(0))
        found = self.editor.find(needle, flags)
        if not found and wrap:
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End if backwards
                                else QTextCursor.MoveOperation.Start)
            self.editor.setTextCursor(cursor)
            found = self.editor.find(needle, flags)
        self.find_status.setText('Found' if found else 'No matches')

    def find_next(self):
        self._find_in_notes(backwards=False)

    def find_previous(self):
        self._find_in_notes(backwards=True)

    def font_context_menu(self, pos):
        menu = QMenu(self)
        family = self.font_choice.currentFont().family()
        action = menu.addAction(f'Use “{family}” as the default font')
        action.triggered.connect(lambda: self.fontSetAsDefault.emit(family))
        menu.exec(self.font_choice.mapToGlobal(pos))

    def paste_plain_text(self):
        """Paste from the system clipboard without importing HTML styling."""
        text = QApplication.clipboard().text()
        if text:
            self.editor.insertPlainText(text)
        self.editor.setFocus()

    def make_list(self, numbered: bool):
        """Build native QTextList items without swallowing selected blank lines.

        Native Qt list objects own the bullets/numbers, their block membership
        and automatic item numbering; no synthetic marker spans are inserted.
        """
        selection = self.editor.textCursor()
        positions = list(self._target_block_positions(selection))
        document = self.editor.document()
        style = QTextListFormat.Style.ListDecimal if numbered else QTextListFormat.Style.ListDisc

        def apply_list():
            transaction = QTextCursor(document)
            transaction.beginEditBlock()
            try:
                for position in positions:
                    block = document.findBlock(position)
                    if not block.isValid():
                        continue
                    # Empty selected paragraphs stay normal separators. A single
                    # empty caret paragraph can intentionally begin a new list.
                    if selection.hasSelection() and _is_visually_blank_paragraph(block.text()):
                        continue
                    existing = block.textList()
                    level = max(1, existing.format().indent()) if existing else 1
                    style_at_level = self._style_for_level(
                        self._list_kind(style), level)
                    if (existing is not None
                            and existing.format().style() == style_at_level):
                        self._normalise_list_block_presentation(block)
                        continue
                    self._put_block_in_list(block, level, style_at_level)
                    self._normalise_list_block_presentation(block)
                self._refresh_list_neighbour_spacing(positions)
            finally:
                transaction.endEditBlock()
            self.editor.setTextCursor(selection)
            self.editor.setFocus()

        self._preserve_editor_view(apply_list)

    def pick_colour(self):
        color = QColorDialog.getColor(self.editor.textColor(), self, 'Text colour')
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            self.apply_format(fmt)
            self.text_colour_button.set_colour(color)

    def pick_highlight(self):
        color = QColorDialog.getColor(QColor('#f3df91'), self, 'Highlight colour')
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            self.apply_format(fmt)
            self.text_highlight_button.set_colour(color)

    def insert_link(self, label: str, target: str, *, force_label=False):
        """Insert an anchor without changing the surrounding typography.

        QTextCursor.insertText with a brand-new QTextCharFormat previously
        reset fonts to Helvetica and left the typing caret inside the link.
        Copy the format at the saved cursor, apply anchor decoration just to
        the inserted characters, then explicitly restore unlinked typing state.
        """
        cursor = self.editor.textCursor()
        # Yomu v0.3.1 hotfix: Copy the effective *typing* style rather than
        # the preceding character (which could already be a pink hyperlink).
        original = QTextCharFormat(self.editor.currentCharFormat())
        original.setAnchor(False)
        original.setAnchorHref('')
        text = label if force_label else (cursor.selectedText() or label)
        link_format = QTextCharFormat(original)
        link_format.setAnchor(True)
        link_format.setAnchorHref(target)
        link_format.setFontUnderline(True)
        link_format.setForeground(QColor('#b64b78'))
        cursor.beginEditBlock()
        cursor.insertText(text, link_format)
        # Yomu v0.3.1 hotfix: A tiny hair space is an actual *non-link*
        # character. It prevents Qt inheriting the link's colour/underline
        # when typing or pressing Return immediately after the arrow.
        # It is not part of the clickable link.
        cursor.insertText('\u200a', original)
        cursor.clearSelection()
        cursor.setCharFormat(original)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        self.editor.setCurrentCharFormat(original)
        self.editor.setFocus()

    def insert_page_link(self, page_id: str, title: str):
        """Use a compact ↗ glyph even when the editor has selected text."""
        cursor = self.editor.textCursor()
        cursor.setPosition(cursor.selectionEnd())
        self.editor.setTextCursor(cursor)
        self.insert_link('↗', f'yomu://page/{page_id}', force_label=True)

    def insert_web_link(self):
        url, ok = QInputDialog.getText(self, 'Insert hyperlink', 'Web address (https://…):')
        if not ok or not url.strip():
            return
        url = url.strip()
        if not (url.startswith('https://') or url.startswith('http://')):
            QMessageBox.warning(self, 'Invalid URL', 'Use an http:// or https:// link.')
            return
        label, ok = QInputDialog.getText(self, 'Link text', 'Display text:', text=url)
        if ok:
            self.insert_link(label.strip() or url, url)

    def open_link(self, target: str):
        if target.startswith(('sumi://page/', 'yomu://page/')):
            self.pageLinkClicked.emit(target.rsplit('/', 1)[-1])
        elif target.startswith(('http://', 'https://')):
            self.externalLinkClicked.emit(target)

    def focus_notes(self):
        self.editor.setFocus()

    def set_web_link_visible(self, enabled: bool):
        """Update toolbar visibility when user changes the preference."""
        self.web_link_button.setVisible(bool(enabled))
