"""Responsive, compact widgets for Yomu Note.

The wrapping layout deliberately avoids fixed-width toolbars. Qt's normal toolbar
will hide excess actions in an overflow popup; here controls remain visible and
wrap into further rows when a pane becomes narrow.
"""
from __future__ import annotations
import time
import math
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QRectF, QSize, QPoint, QTimer, QEasingCurve, QPropertyAnimation, QObject, QEvent, Signal, Property, QVariantAnimation, QUrl
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QFontMetricsF, QPainter, QPainterPath, QLinearGradient, QRadialGradient, QIcon, QPixmap, QPen, QBrush
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QLayout, QSizePolicy, QToolButton, QWidget, QGraphicsOpacityEffect,
                               QLabel, QVBoxLayout, QProgressBar, QPushButton, QGraphicsDropShadowEffect, QMenu, QStyle, QApplication)
from .focus_logic import reminder_slot, finished_session_message, escalating_reminder_message

try:
    from PySide6.QtMultimedia import QSoundEffect
except ImportError:  # The rest of Yomu remains usable on systems lacking audio support.
    QSoundEffect = None




# Small, self-contained line icons use SVG paths rather than a downloaded icon font.
# They stay crisp on HiDPI displays and are coloured to suit the selected theme.
ICON_PATHS = {
    'zoom-in': '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5 M10.5 7.5v6 M7.5 10.5h6"/>',
    'zoom-out': '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5 M7.5 10.5h6"/>',
    'align-left': '<path d="M3 5h18 M3 9h12 M3 13h18 M3 17h12"/>',
    'align-center': '<path d="M3 5h18 M6 9h12 M3 13h18 M6 17h12"/>',
    'align-right': '<path d="M3 5h18 M9 9h12 M3 13h18 M9 17h12"/>',
    'align-justify': '<path d="M3 5h18 M3 9h18 M3 13h18 M3 17h18"/>',
    'list': '<path d="M9 5h12 M9 11h12 M9 17h12"/><circle cx="4" cy="5" r="1"/><circle cx="4" cy="11" r="1"/><circle cx="4" cy="17" r="1"/>',
    'list-ordered': '<path d="M9 5h12 M9 11h12 M9 17h12 M3 4h1v3 M3 11h2v2H3v2h2"/>',
    'table': '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M3 10h18 M3 15h18 M12 4v16"/>',
    'line-spacing': '<path d="M4 5h17 M4 10h17 M4 15h17 M4 20h17 M2 6v12"/>',
    'edit-position': '<path d="M12 3v5 M12 16v5 M3 12h5 M16 12h5"/><circle cx="12" cy="12" r="4"/>',
    'indent': '<path d="M10 5h11 M10 9h11 M10 13h11 M10 17h11 M3 8l4 4-4 4"/>',
    'outdent': '<path d="M10 5h11 M10 9h11 M10 13h11 M10 17h11 M7 8l-4 4 4 4"/>',
    'highlighter': '<path d="m8 5 9 9-4 4-9-9z M16 13l4-4 M3 21h13"/>',
    'link': '<path d="M10 13l4-4 M8 16H7a5 5 0 0 1 0-10h5 M16 8h1a5 5 0 0 1 0 10h-5"/>',
    'palette': '<circle cx="12" cy="12" r="9"/><circle cx="7" cy="10" r="1"/><circle cx="11" cy="6" r="1"/><circle cx="17" cy="9" r="1"/><path d="M13 20c-3-1-3-4-1-5 2-1 4 1 5 0"/>',
    # Annotation-only icons; previously these names fell back to generic dots.
    'mouse-pointer-2': '<path d="M4 3l14 9-7 1-3 7z M11 13l4 7"/>',
    'hand': '<path d="M7 12V7a1.5 1.5 0 0 1 3 0v3-5a1.5 1.5 0 0 1 3 0v5-4a1.5 1.5 0 0 1 3 0v5-2a1.5 1.5 0 0 1 3 0v6c0 3-2 5-5 5h-4c-2 0-3-1-4-3l-3-4a1.6 1.6 0 0 1 3-2l2 2"/>',
    'shapes': '<rect x="2" y="9" width="11" height="11" rx="0"/><circle cx="16.5" cy="7" r="4.5"/><path d="M14 20l3-5 4 5z"/>',
    'eraser': '<path d="m8 4 12 12-5 5H7l-5-5z M5 19l9-10 M11 21h10"/>',
    'link-2': '<path d="M10 13l4-4 M8 16H7a5 5 0 0 1 0-10h5 M16 8h1a5 5 0 0 1 0 10h-5"/>',
    'more': '<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>',
    'fit': '<path d="M4 9V4h5 M15 4h5v5 M20 15v5h-5 M9 20H4v-5"/>',
    'trash-2': '<path d="M3 6h18 M9 6V4h6v2 M6 6l1 15h10l1-15 M10 10v7 M14 10v7"/>',
    'colour': '<path d="M5 20h14 M8 15l4-11 4 11 M9.5 11h5"/>',
}

def line_icon(name: str, color: str = '#58637c') -> QIcon:
    """Render a miniature vector icon into a translucent 24x24 pixmap."""
    path = ICON_PATHS.get(name, ICON_PATHS['more'])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
           f'<g fill="none" stroke="{color}" stroke-width="1.9" stroke-linecap="round" '
           f'stroke-linejoin="round">{path}</g></svg>')
    # Paint SVG at 3x backing resolution; unlike a 24px bitmap, these icons
    # remain crisp when Windows runs at 125%, 150% or 200% DPI. This is a
    # tiny 72x72px transient asset per toolbar icon, never a PDF/page cache.
    backing_scale = 3.0
    pix = QPixmap(int(24 * backing_scale), int(24 * backing_scale))
    pix.setDevicePixelRatio(backing_scale)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer = QSvgRenderer(svg.encode('utf-8'))
    renderer.render(painter, QRectF(0, 0, 24, 24))
    painter.end()
    return QIcon(pix)


class FormattingColourButton(QToolButton):
    """Tiny rich-text colour control with a real-time colour swatch.

    Text colour is shown as a circle; a text highlight is shown as a short
    horizontal bar. Both are readable independently of the selected theme.
    """
    def __init__(self, highlight=False, parent=None):
        super().__init__(parent)
        self.is_highlight = highlight
        self.colour = QColor('#f4d783' if highlight else '#b64b78')
        icon_name = 'highlighter' if highlight else 'colour'
        self.setProperty('yomuIcon', icon_name)
        self.setIcon(line_icon(icon_name))
        self.setIconSize(QSize(17,17))
        self.setFixedSize(31,29)
        self.setToolTip('Change text highlight colour' if highlight else 'Change text colour')

    def set_colour(self, value):
        col = QColor(value)
        if col.isValid():
            self.colour = col
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.colour)
        painter.setPen(QPen(QColor('#677083'), 0.5))
        if self.is_highlight:
            painter.drawRoundedRect(QRect(8, 24, 16, 3), 1.5, 1.5)
        else:
            painter.drawEllipse(QRect(self.width()-11, self.height()-11, 8, 8))
        painter.end()

class ColourDotButton(QToolButton):
    """Single highlight control: left click toggles, right click edits saved colour.

    The dot is drawn separately from the icon so the colour remains readable in
    both dark and light themes without changing the original PDF or page cache.
    """
    colourRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.colour = QColor('#ffcf69')
        self.setIcon(line_icon('highlighter'))
        self.setIconSize(QSize(18,18))
        self.setFixedSize(35,30)
        self.setToolTip('Highlight page · Click to draw; right-click to select colour')
        self.setProperty('yomuIcon', 'highlighter')

    def set_colour(self, value):
        self.colour = QColor(value)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.colourRequested.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.property('annotationCompact'):
            return  # leave room for the group menu arrow in narrow columns
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.colour)
        painter.setPen(QPen(QColor('#647080'), 0.8))
        painter.drawEllipse(QRect(self.width()-12, self.height()-12, 9, 9))
        painter.end()

class FlowLayout(QLayout):
    """A layout that wraps buttons onto a new row as space gets smaller.

    This is why the toolbar still works when the user makes a pane narrow:
    Qt asks this class where each child control should be positioned.
    """
    def __init__(self, parent=None, spacing=5, margins=(0, 0, 0, 0)):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(*margins)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        margins = self.contentsMargins()
        rect = QRect(0, 0, max(1, width - margins.left() - margins.right()), 0)
        return self._arrange(rect, True) + margins.top() + margins.bottom()

    def setGeometry(self, rect):
        super().setGeometry(rect)
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        self._arrange(area, False)

    def _arrange(self, rect, measure):
        x, y = rect.x(), rect.y()
        row_height = 0
        for item in self._items:
            if item.isEmpty():
                continue
            size = item.sizeHint()
            w = min(size.width(), max(1, rect.width()))
            if x > rect.x() and x + w > rect.right() + 1:
                x = rect.x()
                y += row_height + self.spacing()
                row_height = 0
            if not measure:
                item.setGeometry(QRect(QPoint(x, y), QSize(w, size.height())))
            x += w + self.spacing()
            row_height = max(row_height, size.height())
        return y + row_height - rect.y()

    def minimumSize(self):
        margins = self.contentsMargins()
        tallest = max((item.minimumSize().height() for item in self._items), default=0)
        return QSize(1 + margins.left() + margins.right(), tallest + margins.top() + margins.bottom())

    def sizeHint(self):
        return QSize(300, self.heightForWidth(300))


class WrapBar(QWidget):
    """Small toolbar with every action directly visible, even in narrow panes."""
    def __init__(self, label='', parent=None):
        super().__init__(parent)
        self.setObjectName('wrapBar')
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.flow = FlowLayout(self, spacing=4)
        self.setToolTip(label)
        self.buttons = []

    def addWidget(self, widget):
        self.flow.addWidget(widget)
        return widget

    def addSeparator(self):
        # Whitespace between action groups is already provided by FlowLayout.
        return None

    def addIconAction(self, icon_name: str, hint: str, callback=None):
        """Create a compact icon-only button, while retaining an accessible hint."""
        action = QAction(hint, self)
        button = QToolButton(self)
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setIcon(line_icon(icon_name))
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(31, 29)
        button.setToolTip(hint)
        button.setAccessibleName(hint)
        button.setProperty('yomuIcon', icon_name)
        if callback is not None:
            action.triggered.connect(callback)
        self.flow.addWidget(button)
        self.buttons.append(button)
        return action

    def addMenuButton(self, icon_name: str, hint: str, menu: QMenu):
        """Show grouped options through a single icon, avoiding toolbar clutter."""
        button = QToolButton(self)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setIcon(line_icon(icon_name))
        button.setIconSize(QSize(18,18))
        button.setFixedSize(34,29)
        button.setToolTip(hint)
        button.setAccessibleName(hint)
        button.setProperty('yomuIcon', icon_name)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMenu(menu)
        self.flow.addWidget(button)
        self.buttons.append(button)
        return button

    def addAction(self, title):
        action = QAction(title, self)
        button = QToolButton(self)
        button.setAutoRaise(False)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setDefaultAction(action)
        button.setToolTip(title)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.flow.addWidget(button)
        self.buttons.append(button)
        return action


class YomuWordmark(QWidget):
    """A responsive, clickable two-line wordmark with on-demand hover motion.

    The logo's gradient only animates while hovered, preventing constant redraws
    when the application is idle or a different project tab is selected.
    """
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._accent = QColor('#e86483')
        self._second = QColor('#f6a65c')
        self._sub = QColor('#758092')
        self._hover_level = 0.0
        self._flash_level = 0.0
        self._phase = 0.0
        self._reduce_motion = False
        self.setMinimumWidth(110)
        self.setMaximumWidth(190)
        self.setFixedHeight(55)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip('About Yomu Note · click for version and credits')
        self.setAccessibleName('About Yomu Note')
        # Cache system font discovery. Calling QFontDatabase.families() from
        # paintEvent on every frame is slow and may interrogate bitmap fonts.
        fonts = set(QFontDatabase.families())
        self._headline_family = next((f for f in ('Mochiy Pop One', 'Arial Rounded MT Bold',
                              'Hiragino Maru Gothic ProN') if f in fonts), 'Nunito' if 'Nunito' in fonts else 'Sans Serif')
        self._subtitle_family = 'Hiragino Maru Gothic ProN' if 'Hiragino Maru Gothic ProN' in fonts else 'Nunito' if 'Nunito' in fonts else 'Sans Serif'
        self._fade = QPropertyAnimation(self, b'hoverLevel', self)
        self._fade.setDuration(180)
        self._fade.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._end_flash)

    def sizeHint(self):
        return QSize(160, 55)

    def get_hover(self):
        return self._hover_level

    def set_hover(self, value):
        self._hover_level = float(value)
        self.update()

    hoverLevel = Property(float, get_hover, set_hover)

    def set_reduced_motion(self, value: bool):
        self._reduce_motion = bool(value)
        if self._reduce_motion:
            self._timer.stop()
            self._phase = 0
            self.update()

    def _tick(self):
        self._phase = (self._phase + .06) % 1
        self.update()

    def _end_flash(self):
        self._flash_level = 0
        self.update()

    def set_palette(self, accent, second, sub):
        self._accent, self._second, self._sub = QColor(accent), QColor(second), QColor(sub)
        self.update()

    def enterEvent(self, event):
        self._fade.stop()
        self._fade.setStartValue(self._hover_level)
        self._fade.setEndValue(1)
        if self._reduce_motion:
            self.set_hover(1)
        else:
            self._fade.start()
            self._timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._timer.stop()
        self._fade.stop()
        self._fade.setStartValue(self._hover_level)
        self._fade.setEndValue(0)
        if self._reduce_motion:
            self.set_hover(0)
        else:
            self._fade.start()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            if not self._reduce_motion:
                self._flash_level = 1
                self._flash_timer.start(115)
            self.update()
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        label = 'Yomu ❤︎'
        font = QFont(self._headline_family)
        font.setWeight(QFont.Weight.DemiBold)
        font.setPixelSize(min(29, max(16, int(self.width() * .185))))
        while font.pixelSize() > 15 and QFontMetricsF(font).horizontalAdvance(label) > self.width()-7:
            font.setPixelSize(font.pixelSize()-1)
        fm = QFontMetricsF(font)
        path = QPainterPath()
        path.addText((self.width()-fm.horizontalAdvance(label))/2, 5+fm.ascent(), font, label)
        p.save()
        p.translate(0, 2)
        p.scale(1, .86)
        if self._hover_level:
            glow = QColor(self._accent)
            glow.setAlpha(int(90*self._hover_level))
            p.setPen(QPen(glow, 3.4))
            p.drawPath(path)
        slide = self._phase * self.width() if not self._reduce_motion else 0
        gradient = QLinearGradient(-slide, 0, self.width()*2-slide, 0)
        gradient.setColorAt(0, self._accent)
        gradient.setColorAt(.30, self._second)
        gradient.setColorAt(.55, self._accent)
        gradient.setColorAt(.80, self._second)
        gradient.setColorAt(1, self._accent)
        p.fillPath(path, gradient)
        if self._flash_level:
            white = QColor('#ffffff'); white.setAlpha(145)
            p.fillPath(path, white)
        p.restore()
        font = QFont(self._subtitle_family)
        font.setPixelSize(min(12, max(9, int(self.width()*.07))))
        p.setFont(font)
        p.setPen(self._sub)
        p.drawText(QRect(3, 35, self.width()-6, 17), Qt.AlignmentFlag.AlignCenter, 'べんきょうして！')
        p.end()


class SaveToast(QLabel):
    """Short bottom-centred save confirmation with cubic fade-in/out."""
    def __init__(self, parent):
        super().__init__('✿  Notes Saved!  ✿', parent)
        self.setObjectName('saveToast')
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(190, 39)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.opacity = QGraphicsOpacityEffect(self)
        self.opacity.setOpacity(0.0)
        self.setGraphicsEffect(self.opacity)
        self.animation = QPropertyAnimation(self.opacity, b'opacity', self)
        self.animation.setDuration(220)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.hide()
        self.reduced_motion = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fade_out)

    def show_for(self, parent_rect):
        if self.reduced_motion:
            self.animation.stop()
            self.move((parent_rect.width() - self.width()) // 2,
                      parent_rect.height() - self.height() - 16)
            self.opacity.setOpacity(1)
            self.show()
            self.raise_()
            self.timer.start(1500)
            return
        was_visible = self.isVisible()
        self.move((parent_rect.width() - self.width()) // 2, parent_rect.height() - self.height() - 16)
        self.raise_()
        self.show()
        self.timer.stop()
        self.animation.stop()
        self.animation.setStartValue(self.opacity.opacity() if was_visible else 0)
        self.animation.setEndValue(1)
        self.animation.start()
        self.timer.start(1500)

    def fade_out(self):
        if self.reduced_motion:
            self.hide()
            return
        self.animation.stop()
        self.animation.setStartValue(self.opacity.opacity())
        self.animation.setEndValue(0)
        self.animation.start()
        QTimer.singleShot(260, self._maybe_hide)

    def _maybe_hide(self):
        if self.opacity.opacity() < 0.03:
            self.hide()



class FocusFlower(QWidget):
    """Draw one tiny flower that blossoms as a focus session progresses.

    Only the completion animation repaints at animation-frame frequency. Normal
    growth updates once per second with the Pomodoro tick, so this doesn't
    compete with the memory-limited PDF renderer.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(38, 38)
        self.progress = 0.0
        self.bloom = 0.0
        self.colour = QColor('#f391b5')
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(650)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._animate)
        self.setToolTip('A little flower grows as you study ✿')

    def _animate(self, value):
        self.bloom = float(value)
        self.update()

    def set_progress(self, value):
        value = max(0.0, min(1.0, float(value)))
        if abs(value - self.progress) > 0.0003:
            self.progress = value
            self.update()

    def finish(self, reduce_motion=False):
        self.set_progress(1.0)
        if reduce_motion:
            self.bloom = 1.0
            self.update()
        else:
            self.anim.stop()
            self.anim.setStartValue(self.bloom)
            self.anim.setEndValue(1.0)
            self.anim.start()

    def reset(self):
        self.anim.stop()
        self.progress = self.bloom = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#74a87c'), 2.4, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawLine(19, 31, 19, 16)
        painter.setBrush(QColor('#89c69c'))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(11, 24, 9, 5)
        painter.drawEllipse(19, 21, 10, 5)
        scale = max(0.22, self.progress ** .65, self.bloom)
        # Five petals provide a cute, visually meaningful focus-progress meter.
        painter.save()
        painter.translate(19, 15)
        painter.scale(scale, scale)
        painter.setBrush(self.colour)
        for i in range(5):
            painter.save()
            painter.rotate(i * 72)
            painter.drawEllipse(-4, -12, 8, 12)
            painter.restore()
        painter.setBrush(QColor('#ffd77d'))
        painter.drawEllipse(-4, -4, 8, 8)
        painter.restore()
        painter.end()


def _safe_timer_setting(settings, key, default, minimum, maximum):
    """Read a timer number safely, even if settings are damaged.

    A preference file may be edited, truncated, or corrupted.
    Instead of crashing Yomu Note while it starts, use the
    usual default when the number is invalid or out of range.
    """
    try:
        number = int(settings.value(key, default))
    except (ValueError, TypeError, OverflowError):
        number = default
    return max(minimum, min(maximum, number))


class ReadingProgressBar(QProgressBar):
    """HP-style display for a reading ratio; persistence updates immediately.

    Display units are hundredths of a percent, so reading one page out of
    hundreds still nudges the fill. A new target interrupts smoothly from the
    currently painted value. A short glint happens on increases, never decreases.
    The existing Reduce animations preference disables both effects.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 10_000)
        self.setValue(0)
        self._target_units = 0
        self.reduced_motion = False
        self._motion = QPropertyAnimation(self, b'value', self)
        self._motion.setDuration(470)
        self._motion.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._glint = 0.0
        self._flash = QVariantAnimation(self)
        self._flash.setDuration(520)
        self._flash.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._flash.valueChanged.connect(self._set_glint)

    def _set_glint(self, value):
        self._glint = float(value)
        self.update()

    def set_reduced_motion(self, reduced):
        self.reduced_motion = bool(reduced)
        if self.reduced_motion:
            self._motion.stop()
            self._flash.stop()
            self._set_glint(0)
            self.setValue(self._target_units)

    def set_progress(self, percent, *, animate=True, flash=True):
        """Accept a 0..100 percentage, including fractions, for precise fill."""
        target = max(0, min(10_000, round(float(percent) * 100)))
        old_target = self._target_units
        self._target_units = target
        should_animate = animate and not self.reduced_motion and self.isVisible()
        self._motion.stop()
        if not should_animate or self.value() == target:
            self.setValue(target)
        else:
            self._motion.setStartValue(max(0, self.value()))
            self._motion.setEndValue(target)
            self._motion.start()
        self._flash.stop()
        self._set_glint(0)
        if should_animate and flash and target > old_target:
            self._flash.setStartValue(0.48)
            self._flash.setEndValue(0.0)
            self._flash.start()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._glint <= 0 or self.maximum() <= self.minimum():
            return
        fraction = max(0.0, min(1.0, (self.value() - self.minimum()) /
                                  (self.maximum() - self.minimum())))
        if fraction <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # A gentle brightness sweep over the filled region, not the empty
        # track. Painting is limited to this tiny widget during a change.
        filled = QRectF(0, 0, self.width()*fraction, self.height())
        tint = QColor('#ffffff')
        tint.setAlphaF(min(0.55, self._glint))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tint)
        painter.drawRoundedRect(filled, 3, 3)
        painter.end()


class KawaiiNotice(QLabel):
    """A tiny non-modal, theme-coloured message card for reading and Pomodoro.

    PlainText means user-named tabs/groups never become interpreted as HTML.
    This widget neither intercepts clicks nor saves any state into notebooks.
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('kawaiiNotice')
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b'opacity', self)
        self._fade.setDuration(230)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._on_fade_finished)
        self._entrance = QPropertyAnimation(self, b'pos', self)
        self._entrance.setEasingCurve(QEasingCurve.Type.OutBack)
        self._dismiss = QTimer(self)
        self._dismiss.setSingleShot(True)
        self._dismiss.timeout.connect(self._fade_out)
        self._close_on_fade = False
        self._reduced = False
        self.hide()

    def set_palette(self, colours):
        self.setStyleSheet(
            f"QLabel#kawaiiNotice {{ background: {colours['panel']}; "
            f"color: {colours['ink']}; border: 2px solid {colours['accent']}; "
            "border-radius: 13px; padding: 12px 16px; "
            "font-family: 'Nunito'; font-weight: 600; font-size: 12px; }")

    def show_message(self, message, *, header_height=60, duration=4800,
                     reduced_motion=False, playful=False):
        self._reduced = bool(reduced_motion)
        self._dismiss.stop()
        self._fade.stop()
        self._entrance.stop()
        self._close_on_fade = False
        self.setText(str(message))
        # A stable width allows proper wrapping for long final reminders.
        parent = self.parentWidget()
        width = max(170, min(460, parent.width()-28))
        self.setFixedWidth(width)
        self.adjustSize()
        final_pos = QPoint(max(0, (parent.width() - self.width()) // 2),
                           max(8, header_height + 8))
        self.move(final_pos)
        self.raise_()
        self.show()
        if self._reduced:
            self._opacity.setOpacity(1)
        else:
            self._opacity.setOpacity(0)
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.setDuration(280 if playful else 230)
            self._fade.start()
            # Gentle pop upwards, playful mode gets a slightly bigger bounce.
            self._entrance.setDuration(290 if playful else 230)
            self._entrance.setStartValue(final_pos + QPoint(0, 14 if playful else 7))
            self._entrance.setEndValue(final_pos)
            self._entrance.start()
        self._dismiss.start(duration)

    def recenter(self, header_height):
        """Keep an existing toast on-screen when the window is resized."""
        if not self.isVisible():
            return
        self._entrance.stop()
        parent = self.parentWidget()
        self.setFixedWidth(max(170, min(460, parent.width()-28)))
        self.adjustSize()
        self.move(max(0, (parent.width()-self.width())//2),
                  max(8, header_height+8))

    def _fade_out(self):
        if self._reduced:
            self.hide()
            return
        self._fade.stop()
        self._close_on_fade = True
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        self._fade.setDuration(270)
        self._fade.start()

    def _on_fade_finished(self):
        if self._close_on_fade:
            self._close_on_fade = False
            self.hide()


class FocusTimer(QToolButton):
    """Clickable Pomodoro control that updates its display via Qt timers.

    Qt timers send periodic events while keeping the GUI responsive; do not
    sleep inside a QWidget event or block the app while counting down.
    """
    reminder = Signal(str)  # MainWindow shows a non-blocking themed dialogue.

    """Offline Pomodoro with two short E-flat-major chiptune notifications.

    The timer uses ``time.monotonic()`` rather than decrementing a counter, so
    slow frames or a sleeping laptop cannot make a 25-minute session longer.
    Completion sounds repeat at most once per minute for nine further minutes;
    reminders cease ten minutes after the session ends. The timer never plays
    a backlog of missed reminders when a sleeping computer wakes up.
    """
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.durations = {
            'Focus': _safe_timer_setting(settings, 'pomodoroFocus', 25, 1, 180) * 60,
            'Short break': _safe_timer_setting(settings, 'pomodoroShort', 5, 1, 180) * 60,
            'Long break': _safe_timer_setting(settings, 'pomodoroLong', 15, 1, 180) * 60,
        }
        self.mode = 'Focus'
        self.remaining = self.durations[self.mode]
        self.ends_at = None
        self.overdue_mode = None
        self.overdue_since = None
        self.last_reminder_slot = -1
        self.flower = None
        self.sound_enabled = str(settings.value('focusSounds', 'true')).lower() == 'true'
        self.repeat_enabled = str(settings.value('focusRepeat', 'true')).lower() == 'true'
        self.sound_volume = _safe_timer_setting(settings, 'focusVolume', 45, 0, 100)
        self.reduced_motion = str(settings.value('reducedMotion', 'false')).lower() == 'true'
        self._sounds = {}
        self._setup_sounds()
        self.tick = QTimer(self)
        self.tick.setInterval(1000)
        self.tick.timeout.connect(self._step)
        self.clicked.connect(self.toggle)
        self.setFixedWidth(119)
        self.setMinimumHeight(31)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip('Yomu Focus · click to start/pause; right-click to choose a break or reset')
        self._update_display()

    def _setup_sounds(self):
        """Load two bundled WAVs; never fetch audio from a network resource."""
        if QSoundEffect is None:
            return
        resources = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
        for name in ('break', 'study'):
            path = resources / 'assets' / 'audio' / (name + '.wav')
            if path.is_file():
                effect = QSoundEffect(self)
                effect.setSource(QUrl.fromLocalFile(str(path)))
                effect.setLoopCount(1)
                effect.setVolume(self.sound_volume / 100.0)
                self._sounds[name] = effect

    def set_sound_preferences(self, enabled, repeat, volume):
        """Apply user preferences immediately, without restarting the timer."""
        self.sound_enabled = bool(enabled)
        self.repeat_enabled = bool(repeat)
        self.sound_volume = min(100, max(0, int(volume)))
        for effect in self._sounds.values():
            effect.setVolume(self.sound_volume / 100.0)
            if not self.sound_enabled:
                effect.stop()

    def _update_display(self):
        if self.overdue_mode:
            action = 'Break!' if self.overdue_mode == 'Focus' else 'Study!'
            self.setText('🌸 ' + action)
            self.setAccessibleName(action + ' - click to begin the next session')
            return
        mm, ss = divmod(max(0, self.remaining), 60)
        self.setText(f'🍡 {mm:02d}:{ss:02d}' + (' ⏸' if self.ends_at else ''))
        self.setAccessibleName(f'{self.mode}: {mm} minutes and {ss} seconds remaining')

    def _step(self):
        if self.overdue_mode:
            elapsed = max(0.0, time.monotonic() - self.overdue_since)
            slot = reminder_slot(elapsed) if self.repeat_enabled else None
            if slot is not None and slot > self.last_reminder_slot:
                self.last_reminder_slot = slot
                self._notify()
            if slot is None:
                self.tick.stop()  # No timers/audio after the reminder window.
            return
        if self.ends_at is None:
            return
        self.remaining = max(0, math.ceil(self.ends_at - time.monotonic()))
        if self.flower and self.mode == 'Focus':
            duration = max(1, self.durations['Focus'])
            self.flower.set_progress((duration - self.remaining) / duration)
        self._update_display()
        if self.remaining <= 0:
            self.overdue_mode = self.mode
            self.overdue_since = self.ends_at
            self.ends_at = None
            if self.flower and self.mode == 'Focus':
                self.flower.finish(self.reduced_motion)
            self.last_reminder_slot = -1
            # If a laptop wakes after a long sleep, don't suddenly ring for
            # a session that finished more than ten minutes ago.
            slot = reminder_slot(time.monotonic() - self.overdue_since)
            if slot is not None:
                self.last_reminder_slot = slot
                self._notify()
            self._update_display()
            if not self.repeat_enabled or slot is None:
                self.tick.stop()

    def _notify(self):
        sound, _ = finished_session_message(self.overdue_mode)
        message = escalating_reminder_message(self.overdue_mode, max(0, self.last_reminder_slot))
        if self.sound_enabled and sound in self._sounds:
            self._sounds[sound].play()
        self.setToolTip(message + '\nClick to start the next session; right-click for choices.')
        # Keep tooltip for hover/accessibility, but SHOW the reminder in a
        # dedicated non-modal card instead of relying on OS tooltip timeouts.
        self.reminder.emit(message)

    def toggle(self):
        if self.overdue_mode:
            self.select_mode('Short break' if self.overdue_mode == 'Focus' else 'Focus')
        if self.ends_at is not None:
            self._step()
            self.tick.stop()
            self.ends_at = None
        else:
            if self.remaining <= 0:
                self.remaining = self.durations[self.mode]
            self.ends_at = time.monotonic() + self.remaining
            self.tick.start()
        self._update_display()

    def select_mode(self, name):
        """Reset an overdue alert when a user intentionally changes sessions."""
        self.tick.stop()
        self.mode = name
        self.ends_at = None
        self.overdue_mode = self.overdue_since = None
        self.last_reminder_slot = -1
        self.remaining = self.durations[name]
        if self.flower:
            self.flower.reset()
        self._update_display()

    def update_durations(self, focus, short, long):
        self.durations = {'Focus': focus*60, 'Short break': short*60, 'Long break': long*60}
        if self.ends_at is None and not self.overdue_mode:
            self.remaining = self.durations[self.mode]
            self._update_display()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            for name in self.durations:
                menu.addAction(f'Start {name.lower()} ({self.durations[name]//60} min)',
                               lambda _=False, selection=name: self.start_mode(selection))
            menu.addSeparator()
            menu.addAction('Reset current timer', lambda: self.select_mode(self.mode))
            menu.exec(self.mapToGlobal(event.position().toPoint()))
            event.accept()
            return
        super().mousePressEvent(event)

    def start_mode(self, name):
        self.select_mode(name)
        self.toggle()


class ConfettiOverlay(QWidget):
    """Brief, noninteractive flower-coloured confetti for an intentional save.

    Keeps only a dozen tiny particles in memory. It is completely hidden
    between saves and never intercepts mouse clicks or changes any document.
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFixedSize(280, 122)
        self.progress = 0.0
        self.colours = ['#f786a4', '#ffd36f', '#a796ee', '#84cdb0']
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(960)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._step)
        self.anim.finished.connect(self.hide)
        self.particle_count = 24
        self.hide()

    def _step(self, value):
        self.progress = float(value)
        self.update()

    def celebrate(self, parent_rect, reduce_motion=False, *, at_top=False,
                  playful=False, header_height=60, tier='save'):
        if reduce_motion:
            return
        # More confetti for a whole tab / notebook, little sprinkles for a
        # group. Unchanged save celebrations retain the original 24 particles.
        self.particle_count = {'group': 12, 'tab': 24,
                               'notebook': 36}.get(tier, 24)
        if playful and tier != 'save':
            self.particle_count += 8
        duration = {'group': 820, 'tab': 1120, 'notebook': 1390}.get(tier, 960)
        self.anim.stop()  # Safe even if two celebrations happen close together.
        self.anim.setDuration(duration + (150 if playful else 0))
        top = (header_height + 42 if at_top else
               parent_rect.height()-self.height()-24)
        self.move((parent_rect.width()-self.width())//2,
                  max(0, min(parent_rect.height()-self.height(), top)))
        self.raise_()
        self.show()
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self.progress
        count = self.particle_count
        spacing = min(11.4, (self.width()-14) / max(1, count))
        for i in range(count):
            x = self.width()/2 + (i - (count-1)/2)*spacing + math.sin(i*2.3+t*5)*8
            y = self.height()-34 - (31 + (i % 7)*9)*t + 13*t*t
            c = QColor(self.colours[i%len(self.colours)])
            c.setAlphaF(max(0.0, 1.0-t))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(c)
            painter.save()
            painter.translate(x,y)
            painter.rotate((i*35) + t*140)
            if i%7 == 0 and count > 24:
                # A handful of hearts for the grand notebook celebration.
                heart = QPainterPath()
                heart.moveTo(0, 4)
                heart.cubicTo(-8,-2,-5,-6,0,-2)
                heart.cubicTo(5,-6,8,-2,0,4)
                painter.drawPath(heart)
            elif i%3 == 0:
                painter.drawEllipse(-3,-3,6,6)
            else:
                painter.drawRoundedRect(-2,-4,4,8,2,2)
            painter.restore()
        painter.end()


class SoftButtonMotion(QObject):
    """A small, on-demand glow animation for hovered buttons.

    Effects are created only after the first hover, rather than rendering an
    animation continuously. Ease-in/out uses a cubic Bézier-like Qt curve.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.accent = QColor('#df6184')
        self.reduced_motion = False

    def set_accent(self, hex_colour):
        self.accent = QColor(hex_colour)

    def eventFilter(self, obj, event):
        if self.reduced_motion or not isinstance(obj, (QPushButton, QToolButton)):
            return False
        kind = event.type()
        if kind not in (QEvent.Type.Enter, QEvent.Type.Leave,
                        QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            return False
        # Right-click is reserved for context menus and highlight colour;
        # only a left-click produces the transient pressed flash.
        if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease) and event.button() != Qt.MouseButton.LeftButton:
            return False
        effect = getattr(obj, '_yomu_shadow', None)
        if effect is None and obj.graphicsEffect() is not None:
            # Preserve the opacity effect used by the fading page-insert button.
            return False
        if effect is None:
            effect = QGraphicsDropShadowEffect(obj)
            effect.setOffset(0, 0)
            effect.setBlurRadius(0)
            obj.setGraphicsEffect(effect)
            obj._yomu_shadow = effect
            animation = QPropertyAnimation(effect, b'blurRadius', obj)
            animation.setDuration(160)
            animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
            obj._yomu_glow = animation
        colour = QColor(self.accent)
        colour.setAlpha(185 if kind == QEvent.Type.MouseButtonPress else 105)
        effect.setColor(colour)
        glow = obj._yomu_glow
        glow.stop()
        glow.setDuration(105 if kind == QEvent.Type.MouseButtonPress else 190)
        glow.setStartValue(effect.blurRadius())
        glow.setEndValue(17 if kind == QEvent.Type.MouseButtonPress else
                         11 if kind in (QEvent.Type.Enter, QEvent.Type.MouseButtonRelease) and obj.underMouse()
                         else 0)
        glow.start()
        return False
