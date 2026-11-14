"""Collapsible Qt page navigator for Yomu Note v0.7.

This widget only displays and rearranges GROUP METADATA.
It never creates a PDF, modifies an annotation, or renders a page.
The ProjectPane decides whether a proposed rearrangement is valid.

Why use a Qt tree?  A tree is a list where some entries may contain
children.  Qt handles the indentation and disclosure arrows for us.
"""
from __future__ import annotations
import json
from PySide6.QtCore import Qt, Signal, QMimeData, QSize, QRect, QPoint, QPointF, QRectF, QVariantAnimation, QEasingCurve, QAbstractAnimation, QEvent
from PySide6.QtGui import QDrag, QKeySequence, QFont, QPainter, QColor, QIcon, QPalette, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QTreeWidget,
                              QTreeWidgetItem, QStyledItemDelegate,
                              QStyle, QStyleOptionViewItem)


ROLE_KIND = Qt.ItemDataRole.UserRole
ROLE_ID = Qt.ItemDataRole.UserRole + 1
PAGE_MIME = 'application/x-yomu-notebook-pages'
ROLE_ACTIVE = Qt.ItemDataRole.UserRole + 2
ROLE_ACTIVE_ANCESTOR = Qt.ItemDataRole.UserRole + 3
ROLE_PROGRESS = Qt.ItemDataRole.UserRole + 4


class GroupRowDelegate(QStyledItemDelegate):
    """Paint active-page indicators independently of selected items.

    Selection means a page/group is chosen for organisation.
    The accent stripe instead means the page is displayed.
    This separation protects Ctrl/Shift multi-selection.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.accent = QColor('#c74879')

    def sizeHint(self, option, index):
        # The Qt model keeps its real page names and hierarchy; only the
        # painted row height changes.  This works without rebuilding items
        # or loading another thumbnail when the splitter is dragged.
        density = getattr(self.parent(), '_nav_density', 'normal')
        heights = {
            'wide': (55, 86), 'normal': (55, 72), 'compact': (47, 66),
            'rail': (41, 58), 'mini': (38, 51),
        }
        group_height, page_height = heights[density]
        return QSize(48, group_height if index.data(ROLE_KIND) == 'group'
                     else page_height)

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        density = getattr(self.parent(), '_nav_density', 'normal')
        # Keep long names in the data model and accessible tooltips.  In
        # narrow rails a clipped fragment of a long filename is worse than
        # a deliberate, recognisable thumbnail-only row.
        if index.data(ROLE_KIND) == 'page' and density in ('rail', 'mini'):
            option.text = ''
        # Never hide GROUP titles: their labels are loaded directly from
        # metadata, long before (and entirely independently of) thumbnails.
        # Let Qt elide them naturally at narrow widths.

    def _checkbox_rect(self, option, index):
        """Use the *same* style geometry for painting and mouse handling."""
        view = self.parent()
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        if index.data(ROLE_KIND) == 'group':
            styled.rect = option.rect.adjusted(0, 0, 0, -13)
        return view.style().subElementRect(
            QStyle.SubElement.SE_ItemViewItemCheckIndicator, styled, view)

    def checkbox_hit_rect(self, option, index):
        """A generous invisible target (roughly 28×30), inside its row.

        The checkbox artwork remains 16px.  Expanding the *hit* rectangle
        is safer than intercepting the entire row, which would break page
        selection, folder collapse and drag-and-drop.
        """
        indicator = self._checkbox_rect(option, index)
        if indicator.width() < 8 or indicator.height() < 8:
            return QRect()
        row = (option.rect.adjusted(0, 0, 0, -13)
               if index.data(ROLE_KIND) == 'group' else option.rect)
        return indicator.adjusted(-7, -8, 7, 8).intersected(row)

    def editorEvent(self, event, model, option, index):
        """Let clicks near the box toggle it; preserve Qt keyboard support.

        The owning ProjectPane still records one Undo step through the
        existing itemChanged/readToggled signal.  Rebuilding remains
        deferred until after the mouse event, just as in v0.7.2a.
        """
        mouse_events = (QEvent.Type.MouseButtonPress,
                        QEvent.Type.MouseButtonRelease,
                        QEvent.Type.MouseButtonDblClick)
        if (event.type() in mouse_events and
                index.flags() & Qt.ItemFlag.ItemIsUserCheckable and
                index.flags() & Qt.ItemFlag.ItemIsEnabled and
                event.button() == Qt.MouseButton.LeftButton and
                self.checkbox_hit_rect(option, index).contains(
                    event.position().toPoint())):
            if event.type() == QEvent.Type.MouseButtonRelease:
                current = index.data(Qt.ItemDataRole.CheckStateRole)
                state = (current.value if hasattr(current, 'value')
                         else current)
                new = (Qt.CheckState.Unchecked
                       if state == Qt.CheckState.Checked.value
                       else Qt.CheckState.Checked)
                model.setData(index, new, Qt.ItemDataRole.CheckStateRole)
            return True
        return super().editorEvent(event, model, option, index)

    def _paint_read_indicator(self, painter, option, index):
        """Colour only the read/unread boxes using the active Qt theme.

        Qt's native tree checkmarks can stay bright white on Windows even
        when Yomu selects a light theme.  The delegate paints over that
        *visual* indicator; Qt still owns the checkbox hit area, its state,
        keyboard activation and the existing single-step Undo signal.
        """
        view = self.parent()
        if view is None:
            return
        # Identical geometry to editorEvent() — no invisible mismatch
        # between what looks clickable and what actually toggles.
        indicator = self._checkbox_rect(option, index)
        if indicator.width() < 8 or indicator.height() < 8:
            return
        side = min(indicator.width(), indicator.height(), 16)
        x = indicator.x() + (indicator.width() - side) / 2
        y = indicator.y() + (indicator.height() - side) / 2
        rect = QRectF(x + 0.5, y + 0.5, side - 1, side - 1)
        palette = view.palette()
        paper = palette.color(QPalette.ColorRole.Base)
        # Tint unchecked boxes instead of relying on the system's brilliant
        # white native checkbox.  This also works for every dark palette.
        fill = QColor(
            round(paper.red() * 0.78 + self.accent.red() * 0.22),
            round(paper.green() * 0.78 + self.accent.green() * 0.22),
            round(paper.blue() * 0.78 + self.accent.blue() * 0.22))
        raw_state = index.data(Qt.ItemDataRole.CheckStateRole)
        # PySide6 can return either an enum or its integer value here.
        # Normalising prevents a solid checkbox with an invisible tick.
        try:
            state = Qt.CheckState(int(raw_state.value if hasattr(raw_state, 'value') else raw_state))
        except (ValueError, TypeError):
            state = Qt.CheckState.Unchecked
        active = state in (Qt.CheckState.Checked, Qt.CheckState.PartiallyChecked)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(self.accent, 1.5))
        painter.setBrush(self.accent if active else fill)
        painter.drawRoundedRect(rect, 3, 3)
        if active:
            # Contrast against the actual ACCENT fill, not the OS light-mode
            # checkbox style. Use the brighter of black/white by WCAG luminance.
            def channel(value):
                value = value / 255.0
                return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055)**2.4
            luminance = (0.2126 * channel(self.accent.red()) +
                         0.7152 * channel(self.accent.green()) +
                         0.0722 * channel(self.accent.blue()))
            mark = QColor('#202027') if luminance > 0.18 else QColor('#ffffff')
            pen = QPen(mark, max(2.5, side * 0.17))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            if state == Qt.CheckState.PartiallyChecked:
                painter.drawLine(QPointF(x + side * 0.26, y + side * 0.50),
                                 QPointF(x + side * 0.74, y + side * 0.50))
            else:
                painter.drawLine(QPointF(x + side * 0.23, y + side * 0.51),
                                 QPointF(x + side * 0.43, y + side * 0.70))
                painter.drawLine(QPointF(x + side * 0.43, y + side * 0.70),
                                 QPointF(x + side * 0.78, y + side * 0.30))
        painter.restore()

    def paint(self, painter, option, index):
        # Paint text and Qt's native checkbox normally.  A slim progress
        # bar occupies space BELOW a folder's label, not its title.
        if index.data(ROLE_KIND) == 'group':
            compact = QStyleOptionViewItem(option)
            compact.rect = option.rect.adjusted(0, 0, 0, -13)
            super().paint(painter, compact, index)
            counts = index.data(ROLE_PROGRESS)
            if counts and counts[1]:
                from .reading_progress import percentage
                done, total = counts
                view = self.parent()
                group_id = index.data(ROLE_ID)
                ratio = view.group_display_ratio(group_id, done, total)
                density = getattr(view, '_nav_density', 'normal')
                # Compact group rows keep an actual progress line instead
                # of showing a clipped percent counter or horizontal scroll.
                # Measure the counter instead of reserving a fixed 64 px.
                # '280/280 · 100%' otherwise runs ON TOP of the meter.
                left = option.rect.left() + (8 if density in ('rail', 'mini') else 15)
                right = option.rect.right() - 8
                bottom = option.rect.bottom() - 5
                display = ''
                counter_rect = QRect()
                if density not in ('rail', 'mini'):
                    counter_font = QFont('Montserrat', 8)
                    painter.save()
                    painter.setFont(counter_font)
                    full = f'{done}/{total} · {percentage(done, total)}%'
                    short = f'{percentage(done, total)}%'
                    available = max(0, right - left)
                    display = (full if density != 'compact' and available >= 180
                               else short if available >= 80 else '')
                    text_width = painter.fontMetrics().horizontalAdvance(display) + 10 if display else 0
                    painter.restore()
                    counter_rect = QRect(right - text_width, bottom - 10,
                                         text_width, 14)
                    right -= text_width + (8 if display else 0)
                bar = QRect(left, bottom - 2, max(0, right - left), 4)
                if bar.width() > 4:
                    painter.save()
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor('#9a9a9a'))
                    painter.setOpacity(0.30)
                    painter.drawRoundedRect(bar, 2, 2)
                    painter.setOpacity(1.0)
                    painted = QRect(bar)
                    painted.setWidth(round(bar.width() * ratio))
                    painter.setBrush(self.accent)
                    painter.drawRoundedRect(painted, 2, 2)
                    # Only increases get a short 'HP gained' gleam.
                    if view.group_is_increasing(group_id) and view._group_anim.state() == QAbstractAnimation.State.Running:
                        painter.setOpacity(max(0, 0.34 * (1-view._group_animation_t)))
                        painter.setBrush(QColor('#ffffff'))
                        painter.drawRoundedRect(painted, 2, 2)
                        painter.setOpacity(1.0)
                    if display:
                        painter.setPen(self.accent)
                        painter.setFont(QFont('Montserrat', 8))
                        painter.drawText(counter_rect,
                            Qt.AlignmentFlag.AlignRight |
                            Qt.AlignmentFlag.AlignVCenter, display)
                    painter.restore()
        else:
            view = self.parent()
            density = getattr(view, '_nav_density', 'normal')
            if density in ('normal', 'wide', 'compact'):
                # Native delegate draws actual DisplayRole text first, even
                # before any thumbnail has been decoded.
                super().paint(painter, option, index)
            else:
                # Let Qt draw focus, selection and the *real checkbox*;
                # arrange the existing cached thumbnail centrally in the
                # remaining room rather than squeezing a long filename.
                styled = QStyleOptionViewItem(option)
                self.initStyleOption(styled, index)
                styled.icon = QIcon()
                thumbnail = index.data(Qt.ItemDataRole.DecorationRole)
                if not isinstance(thumbnail, QIcon) or thumbnail.isNull():
                    # No image yet? A short text label is MUCH better than an
                    # entirely blank page row while thumbnail work is queued.
                    styled.text = str(index.data(Qt.ItemDataRole.DisplayRole) or '')
                view.style().drawControl(QStyle.ControlElement.CE_ItemViewItem,
                                         styled, painter, view)
                icon = index.data(Qt.ItemDataRole.DecorationRole)
                if isinstance(icon, QIcon) and not icon.isNull():
                    indicator = self._checkbox_rect(option, index)
                    left = max(option.rect.left() + 2, indicator.right() + 5)
                    available = option.rect.right() - left - 3
                    if available >= 12:
                        icon_size = view.iconSize()
                        pic = icon.pixmap(QSize(min(icon_size.width(), available),
                                                min(icon_size.height(), option.rect.height()-6)))
                        if not pic.isNull():
                            x = left + (available - pic.width()) // 2
                            y = option.rect.top() + (option.rect.height()-pic.height()) // 2
                            painter.save()
                            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                            painter.drawPixmap(QPoint(x, y), pic)
                            painter.restore()
        # Overlay just the checkbox in the same native hit rectangle.
        self._paint_read_indicator(
            painter, option, index)
        if not (index.data(ROLE_ACTIVE) or
                index.data(ROLE_ACTIVE_ANCESTOR)):
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.accent)
        rect = option.rect
        if index.data(ROLE_ACTIVE):
            painter.drawRoundedRect(
                QRect(rect.left() + 2, rect.top() + 5,
                      4, max(5, rect.height() - 10)), 2, 2)
        else:
            # A collapsed folder gets a dot if it contains the
            # active page.  We do not expand it automatically.
            painter.drawEllipse(rect.right() - 11,
                                rect.center().y() - 3, 6, 6)
        painter.restore()




class PageGroupsTree(QTreeWidget):
    """One editable-looking tree, with validation delegated to its owner."""
    structureChanged = Signal()
    collapseChanged = Signal(str, bool)
    pageActivated = Signal(str)
    filesDropped = Signal(list, int, object)
    pagesPasted = Signal(str, str, list, bool)
    readToggled = Signal(str, str, bool)
    groupMoveRequested = Signal(str, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setViewportMargins(4, 3, 4, 4)
        self.setColumnCount(1)
        self._nav_density = 'normal'
        self.setIndentation(17)
        self.setUniformRowHeights(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setItemDelegate(GroupRowDelegate(self))
        self.setIconSize(QSize(44, 58))
        self._active_page_id = None
        self._active_painted = []
        self._thumb_ids = set()
        self._check_states = {}
        # A single 420ms animation drives the visible progress bars for ALL
        # groups/subgroups. It tracks stable group IDs, never tree item objects.
        # No per-folder animation timer and no extra thumbnails or PDF loads.
        self._group_ratio_start = {}
        self._group_ratio_end = {}
        self._group_animation_t = 1.0
        self._reduce_reading_motion = False
        self._group_anim = QVariantAnimation(self)
        self._group_anim.setDuration(420)
        self._group_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._group_anim.valueChanged.connect(self._animate_group_bars)
        self.setAnimated(False)  # No expand animation for huge notebooks.
        self.setAlternatingRowColors(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._rebuilding = False
        self._last_tree = []
        self.itemClicked.connect(self._clicked)
        self.itemChanged.connect(self._read_check_changed)
        self.itemExpanded.connect(lambda item: self._collapse(item, False))
        self.itemCollapsed.connect(lambda item: self._collapse(item, True))

    def set_navigator_density(self, width):
        """Switch presentation, not the underlying tree or cached images.

        Wide/Normal: filenames and thumbnails; Compact: group names and
        centred page icons; Rail: minimal folder/check/progress; Mini: slim rail.
        Re-evaluating at thresholds (not for every drag pixel) also keeps
        100+ page notebooks responsive when the splitter is resized.
        """
        density = ('mini' if width < 100 else 'rail' if width < 160
                   else 'compact' if width < 248 else 'normal' if width < 310
                   else 'wide')
        if density == self._nav_density:
            return
        self._nav_density = density
        self.setIndentation({'wide': 17, 'normal': 17, 'compact': 12,
                             'rail': 7, 'mini': 0}[density])
        self.setIconSize({'wide': QSize(58, 76), 'normal': QSize(44, 58),
                          'compact': QSize(36, 47),
                          'rail': QSize(28, 36),
                          'mini': QSize(19, 27)}[density])
        # All row heights come from the delegate, never per-item size hints.
        self.doItemsLayout()
        self.viewport().update()

    def set_accent(self, accent):
        # The active indicator follows the current app theme.
        self.itemDelegate().accent = QColor(accent)
        self.viewport().update()

    def set_reading_reduced_motion(self, reduced):
        self._reduce_reading_motion = bool(reduced)
        if reduced:
            self._group_anim.stop()
            self._group_animation_t = 1.0
            self.viewport().update()

    def _animate_group_bars(self, value):
        self._group_animation_t = float(value)
        self.viewport().update()  # Qt repaints just the rows in the viewport.

    def group_display_ratio(self, identifier, done, total):
        end = self._group_ratio_end.get(identifier, done / total if total else 0)
        start = self._group_ratio_start.get(identifier, end)
        return start + (end - start) * self._group_animation_t

    def group_is_increasing(self, identifier):
        return (self._group_ratio_end.get(identifier, 0) >
                self._group_ratio_start.get(identifier, 0))

    def _read_check_changed(self, item, _column):
        """Qt updates the checkbox first; the owning tab records Undo.

        Do not modify sibling checkboxes here.  That would emit a storm
        of itemChanged signals and create one Undo per descendant.
        """
        if self._rebuilding:
            return
        kind = item.data(0, ROLE_KIND)
        identifier = item.data(0, ROLE_ID)
        if kind not in ('page', 'group') or not identifier:
            return
        # Qt emits itemChanged for *every* data role, including our
        # active-page highlight stripe and collapsed-ancestor dot.
        # Without this comparison, navigating pages could accidentally
        # mark them read or unread merely by repainting the view!
        key = kind, identifier
        state = item.checkState(0)
        if self._check_states.get(key) == state:
            return
        self._check_states[key] = state
        self.readToggled.emit(
            kind, identifier, state == Qt.CheckState.Checked)

    def _clicked(self, item, _column):
        if not self._rebuilding and item.data(0, ROLE_KIND) == 'page':
            self.pageActivated.emit(item.data(0, ROLE_ID))

    def _collapse(self, item, collapsed):
        if not self._rebuilding and item.data(0, ROLE_KIND) == 'group':
            self.collapseChanged.emit(item.data(0, ROLE_ID), collapsed)

    def load_tree(self, groups, pages, active_page=None, read_ids=()):
        """Rebuild Qt items from stable IDs, without changing project data."""
        by_id = {page['id']: page for page in pages}
        read = set(read_ids)
        # Interruption-safe start values, keyed by stable ID instead of deleted
        # QTreeWidgetItems; never animate the first load from a false zero.
        old_ratios = {identifier: self.group_display_ratio(identifier, 0, 0)
                      for identifier in self._group_ratio_end}
        self._group_anim.stop()
        next_ratios = {}
        self._rebuilding = True
        try:
            self.clear()
            # Qt deletes the old items during clear().  Never keep an
            # item pointer from the previous model after rebuilding.
            self._active_painted.clear()
            self._thumb_ids.clear()
            self._check_states.clear()
            self._last_tree = groups

            def fill(parent, nodes):
                for node in nodes:
                    if node['type'] == 'group':
                        item = QTreeWidgetItem([node['name']])
                        group_font = QFont('Montserrat', 9)
                        group_font.setPointSizeF(8.8)
                        group_font.setWeight(QFont.Weight.Bold)
                        item.setFont(0, group_font)
                        item.setData(0, ROLE_KIND, 'group')
                        from .reading_progress import group_counts
                        completed, total = group_counts(node, read)
                        next_ratios[node['id']] = completed / total if total else 0.0
                        item.setData(0, ROLE_PROGRESS, (completed, total))
                        self._check_states[('group', node['id'])] = (
                            Qt.CheckState.Checked if total and completed == total
                            else Qt.CheckState.PartiallyChecked if completed
                            else Qt.CheckState.Unchecked)
                        item.setCheckState(0, (
                            Qt.CheckState.Checked if total and completed == total
                            else Qt.CheckState.PartiallyChecked if completed
                            else Qt.CheckState.Unchecked))
                        item.setData(0, ROLE_ID, node['id'])
                        item.setToolTip(
                            0, node['name'] + f' · {completed}/{total} read'
                            ' · Drag to organise; tick to mark all read')
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled
                                      | Qt.ItemFlag.ItemIsDropEnabled)
                        if parent is None:
                            self.addTopLevelItem(item)
                        else:
                            parent.addChild(item)
                        fill(item, node['children'])
                        item.setExpanded(not node['collapsed'])
                    else:
                        pid = node['page_id']
                        title = by_id.get(pid, {}).get('title', 'Missing page')
                        item = QTreeWidgetItem([title])
                        page_font = QFont('Montserrat')
                        page_font.setPointSizeF(8.7)
                        item.setFont(0, page_font)
                        item.setData(0, ROLE_KIND, 'page')
                        item.setCheckState(0,
                            Qt.CheckState.Checked if pid in read
                            else Qt.CheckState.Unchecked)
                        self._check_states[('page', pid)] = item.checkState(0)
                        item.setData(0, ROLE_ID, pid)
                        item.setToolTip(0, title + ' · Tick to mark read')
                        # A page may be dropped BETWEEN others, but cannot
                        # contain child items.  Only folders accept children.
                        item.setFlags((item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
                                      & ~Qt.ItemFlag.ItemIsDropEnabled)
                        if parent is None:
                            self.addTopLevelItem(item)
                        else:
                            parent.addChild(item)
            fill(None, groups)
            self.mark_active(active_page)
        finally:
            self._rebuilding = False
        self._group_ratio_end = next_ratios
        self._group_ratio_start = {identifier: old_ratios.get(identifier, end)
                                   for identifier, end in next_ratios.items()}
        changing = any(abs(self._group_ratio_start[k] - end) > 0.00001
                       for k, end in next_ratios.items())
        if changing and self.isVisible() and not self._reduce_reading_motion:
            self._group_animation_t = 0.0
            self._group_anim.setStartValue(0.0)
            self._group_anim.setEndValue(1.0)
            self._group_anim.start()
        else:
            self._group_animation_t = 1.0
        self.viewport().update()

    def mark_active(self, page_id):
        """Highlight the displayed page without changing selection.

        The page can belong to a collapsed folder.  In that case,
        mark the nearest visible folder with a small accent dot.
        """
        # Only repaint the previously highlighted entries; walking
        # every page for every arrow-key press would slow long books.
        for kind, identifier, role in self._active_painted:
            # Drag-and-drop can replace Qt item wrappers.  Resolve a
            # fresh item by ID instead of retaining a deleted object.
            item = self.find_item(kind, identifier)
            if item is not None:
                item.setData(0, role, False)
        self._active_painted.clear()
        self._active_page_id = page_id
        target = self.find_item('page', page_id)
        if target is None:
            self.viewport().update()
            return
        ancestor = target.parent()
        visible = target
        while ancestor is not None:
            if not ancestor.isExpanded():
                visible = ancestor
            ancestor = ancestor.parent()
        if visible is target:
            target.setData(0, ROLE_ACTIVE, True)
            self._active_painted.append(('page', page_id, ROLE_ACTIVE))
        else:
            visible.setData(0, ROLE_ACTIVE_ANCESTOR, True)
            self._active_painted.append(('group', visible.data(0, ROLE_ID),
                                         ROLE_ACTIVE_ANCESTOR))
        if not self._rebuilding:
            self.scrollToItem(visible)
        self.viewport().update()

    def selected_group_id(self):
        """Only a deliberately selected folder is an import target.

        ``currentItem`` is not enough.  Keyboard navigation might
        change the current page while a group remains selected.
        """
        selected = self.selectedItems()
        if len(selected) != 1:
            return None
        item = selected[0]
        return (item.data(0, ROLE_ID)
                if item.data(0, ROLE_KIND) == 'group' else None)

    def visible_page_ids(self, limit=20):
        """Locate visible page rows; avoid decoding a whole notebook.

        Collapsed descendants do not appear in indexBelow().
        """
        result = []
        # The middle of the row avoids empty tree indentation space.
        viewport = self.viewport()
        index = self.indexAt(QPoint(max(1, viewport.width() // 2), 7))
        if not index.isValid():
            index = self.indexAt(viewport.rect().center())
        if not index.isValid():
            return result
        max_y = self.viewport().height() + 90
        steps = 0
        while index.isValid() and steps < limit + 24:
            rect = self.visualRect(index)
            if rect.top() > max_y:
                break
            if rect.bottom() >= -70 and index.data(ROLE_KIND) == 'page':
                result.append(index.data(ROLE_ID))
                if len(result) >= limit:
                    break
            index = self.indexBelow(index)
            steps += 1
        return result

    def set_page_thumbnail(self, page_id, pixmap):
        """Display one cached image without keeping full-sized art."""
        item = self.find_item('page', page_id)
        if item is None or pixmap.isNull():
            return
        scaled = pixmap.scaled(QSize(58, 76),
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        item.setIcon(0, QIcon(scaled))
        self._thumb_ids.add(page_id)

    def discard_other_thumbnails(self, keep):
        """Remove offscreen icons to respect the in-memory cap."""
        for pid in self._thumb_ids - set(keep):
            item = self.find_item('page', pid)
            if item is not None:
                item.setIcon(0, QIcon())
        self._thumb_ids.intersection_update(keep)

    def find_item(self, kind, identifier):
        def walk(item):
            if item.data(0, ROLE_KIND) == kind and item.data(0, ROLE_ID) == identifier:
                return item
            for index in range(item.childCount()):
                found = walk(item.child(index))
                if found is not None:
                    return found
            return None
        for index in range(self.topLevelItemCount()):
            found = walk(self.topLevelItem(index))
            if found is not None:
                return found
        return None

    def selected_page_ids(self):
        """Return selected page IDs in *reading* order, not click order."""
        selected = {i.data(0, ROLE_ID) for i in self.selectedItems()
                    if i.data(0, ROLE_KIND) == 'page'}
        return [pid for pid in self.flatten_items() if pid in selected]

    def flatten_items(self):
        result = []
        def walk(item):
            if item.data(0, ROLE_KIND) == 'page':
                result.append(item.data(0, ROLE_ID))
            else:
                for j in range(item.childCount()):
                    walk(item.child(j))
        for i in range(self.topLevelItemCount()):
            walk(self.topLevelItem(i))
        return result

    def extract_tree(self):
        """Describe the UI's proposed order for safe model validation."""
        def walk(item):
            kind = item.data(0, ROLE_KIND)
            if kind == 'page':
                return {'type': 'page', 'page_id': item.data(0, ROLE_ID)}
            return {'type': 'group', 'id': item.data(0, ROLE_ID),
                    'name': item.text(0),
                    'collapsed': not item.isExpanded(),
                    'children': [walk(item.child(j)) for j in range(item.childCount())]}
        return [walk(self.topLevelItem(i)) for i in range(self.topLevelItemCount())]

    def startDrag(self, actions):
        """Include page IDs so original cross-tab copy/paste still works."""
        selected = self.selected_page_ids()
        if not selected or not getattr(self, 'notebook_id', None):
            super().startDrag(actions)
            return
        mime = self.model().mimeData(self.selectedIndexes())
        mime.setData(PAGE_MIME, json.dumps({
            'notebook': self.notebook_id,
            'source': self.tab_id,
            'pages': selected,
        }).encode('utf8'))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction,
                  Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasFormat(PAGE_MIME):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls():
            # Compute the insertion point BEFORE importing.  The actual
            # importer still runs through the existing background worker.
            paths = [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]
            if paths:
                target = self.itemAt(event.position().toPoint())
                order = self.flatten_items()
                index = len(order)
                if target is not None:
                    if target.data(0, ROLE_KIND) == 'page':
                        index = order.index(target.data(0, ROLE_ID))
                    else:
                        first = self._first_descendant_page(target)
                        if first in order:
                            index = order.index(first)
                group_id = (target.data(0, ROLE_ID)
                            if target is not None and
                            target.data(0, ROLE_KIND) == 'group'
                            else None)
                self.filesDropped.emit(paths, index, group_id)
                event.acceptProposedAction()
            else:
                event.ignore()
            return
        if mime.hasFormat(PAGE_MIME):
            try:
                data = json.loads(bytes(mime.data(PAGE_MIME)).decode('utf8'))
                if (data['notebook'] == self.notebook_id
                        and data['source'] != self.tab_id):
                    self.pagesPasted.emit(data['source'], self.tab_id,
                                          data['pages'], event.dropAction() == Qt.DropAction.CopyAction)
                    event.acceptProposedAction()
                    return
            except (KeyError, TypeError, ValueError):
                event.ignore()
                return
        # Handle ONE dragged folder through the validated Python model,
        # not by letting Qt mutate its item tree first.  A Qt item move
        # can otherwise leave its widget state partially changed when
        # validation rejects the drop, particularly for nested folders.
        selected = self.selectedItems()
        if (len(selected) == 1 and
                selected[0].data(0, ROLE_KIND) == 'group'):
            moving_id = selected[0].data(0, ROLE_ID)
            target = self.itemAt(event.position().toPoint())
            indicator = self.dropIndicatorPosition()
            where = QAbstractItemView.DropIndicatorPosition
            if target is None or indicator == where.OnViewport:
                parent_id = None
                index = self.topLevelItemCount()
            elif indicator == where.OnItem:
                if target.data(0, ROLE_KIND) != 'group':
                    event.ignore()
                    return
                parent_id = target.data(0, ROLE_ID)
                index = target.childCount()
            else:
                parent = target.parent()
                parent_id = (parent.data(0, ROLE_ID)
                             if parent is not None else None)
                index = (parent.indexOfChild(target)
                         if parent is not None
                         else self.indexOfTopLevelItem(target))
                if indicator == where.BelowItem:
                    index += 1
            self.groupMoveRequested.emit(moving_id, parent_id, index)
            event.acceptProposedAction()
            return
        super().dropEvent(event)
        if event.isAccepted():
            self.structureChanged.emit()

    @staticmethod
    def _first_descendant_page(item):
        if item.data(0, ROLE_KIND) == 'page':
            return item.data(0, ROLE_ID)
        for i in range(item.childCount()):
            found = PageGroupsTree._first_descendant_page(item.child(i))
            if found is not None:
                return found
        return None

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            selected = self.selected_page_ids()
            if selected and getattr(self, 'notebook_id', None):
                mime = QMimeData()
                mime.setData(PAGE_MIME, json.dumps({
                    'notebook': self.notebook_id,
                    'source': self.tab_id,
                    'pages': selected,
                }).encode('utf8'))
                QApplication.clipboard().setMimeData(mime)
                event.accept()
                return
        if event.matches(QKeySequence.StandardKey.Paste):
            mime = QApplication.clipboard().mimeData()
            if mime and mime.hasFormat(PAGE_MIME):
                try:
                    data = json.loads(bytes(mime.data(PAGE_MIME)).decode('utf8'))
                    if data['notebook'] == self.notebook_id:
                        self.pagesPasted.emit(data['source'], self.tab_id,
                                              data['pages'], True)
                        event.accept()
                        return
                except (KeyError, ValueError, TypeError):
                    pass
        super().keyPressEvent(event)
