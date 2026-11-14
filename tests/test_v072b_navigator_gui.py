"""Native Qt interaction tests. Run on Windows/macOS with PySide6 installed."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
from PySide6.QtTest import QTest
from yomunote.page_groups import group_node, page_node
from yomunote.page_groups_ui import PageGroupsTree, ROLE_ID
from yomunote.ui import KawaiiNotice
from yomunote.window import THEMES


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tree(app):
    group = group_node('Week 8 Lecture Slides', [page_node('a'), page_node('b')])
    view = PageGroupsTree()
    view.load_tree([group], [{'id':'a','title':'Really long lecture slide title'},
                             {'id':'b','title':'A second slide'}])
    view.resize(340, 400)
    view.show()
    app.processEvents()
    yield view
    view.close()


def test_oversized_checkbox_target_toggles_without_clicking_its_visible_square(tree, app):
    page = tree.find_item('page', 'a')
    index = tree.indexFromItem(page)
    option = QStyleOptionViewItem()
    option.rect = tree.visualRect(index)
    indicator = tree.itemDelegate()._checkbox_rect(option, index)
    target = tree.itemDelegate().checkbox_hit_rect(option, index)
    assert target.width() > indicator.width()
    assert target.height() > indicator.height()
    assert tree.visualRect(index).contains(target.center())
    # A point just to the left of the square is still an intentional tap.
    click = QPoint(indicator.left()-3, indicator.center().y())
    assert target.contains(click) and not indicator.contains(click)
    seen = []
    tree.readToggled.connect(lambda *args: seen.append(args))
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=click)
    app.processEvents()
    assert page.checkState(0) == Qt.CheckState.Checked
    assert seen == [('page', 'a', True)]
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=click)
    app.processEvents()
    assert page.checkState(0) == Qt.CheckState.Unchecked


@pytest.mark.parametrize('width,density', [(420,'wide'), (275,'normal'),
                                           (218,'compact'), (135,'rail'), (80,'mini')])
def test_navigator_density_preserves_page_names_and_icons(tree, app, width, density):
    page = tree.find_item('page','a')
    icon = QPixmap(58, 76); icon.fill(QColor('red'))
    tree.set_page_thumbnail('a', icon)
    tree.resize(width, 400)
    tree.set_navigator_density(width)
    app.processEvents()
    assert tree._nav_density == density
    assert page.text(0) == 'Really long lecture slide title'
    assert not page.icon(0).isNull()
    assert tree.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert not tree.viewport().grab().isNull()


def test_notice_has_valid_theme_qss(app):
    from PySide6.QtWidgets import QWidget
    parent = QWidget(); parent.show()
    notice = KawaiiNotice(parent)
    for name in ('strawberry','melon-soda','grape-fizz','arcade-hearts'):
        notice.set_palette(THEMES[name])
        assert notice.styleSheet().strip().endswith('}')
        assert not notice.styleSheet().strip().endswith('}}')
    parent.close()
