"""Qt offscreen smoke test for v0.4.1's centred, aspect-preserving shelf.

Run on Windows/macOS with PySide6; skipped automatically if unavailable.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest
QtCore = pytest.importorskip('PySide6.QtCore')
QtGui = pytest.importorskip('PySide6.QtGui')
QtWidgets = pytest.importorskip('PySide6.QtWidgets')
from yomunote.window import ProjectPane
from yomunote.importers import blank_page
from yomunote.project import Project


def test_delegate_paints_landscape_preview_in_card_middle():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    with TemporaryDirectory() as tmp:
        project = Project.create(Path(tmp), 'Aspect test')
        project.pages.append(blank_page(project))
        project.save()
        settings = QtCore.QSettings(str(Path(tmp) / 's.ini'), QtCore.QSettings.Format.IniFormat)
        pane = ProjectPane(project, settings)
        pane.resize(1200, 850)
        pane.show()
        app.processEvents()
        pane._thumb_timer.stop()  # prevent blank-page worker replacing the test image
        page = pane.pages_list.item(0)
        wide = QtGui.QPixmap(190, 55)
        wide.fill(QtGui.QColor('#ee0088'))
        page.setData(QtCore.Qt.ItemDataRole.DecorationRole, wide)
        # Render only the list viewport; the pink rectangle should appear
        # centred in the image area, *not* at its top or stretched upright.
        result = QtGui.QImage(pane.pages_list.viewport().size(),
                              QtGui.QImage.Format.Format_ARGB32)
        result.fill(QtGui.QColor('white'))
        pane.pages_list.viewport().render(result)
        rect = pane.pages_list.visualItemRect(page)
        x = rect.center().x()
        image_zone_top = rect.top() + 7
        image_zone_bottom = rect.bottom() - 33
        image_middle = (image_zone_top + image_zone_bottom) // 2
        # The centre of the content should be pink and distant points above
        # and below should not be that colour; the page must stay landscape.
        assert result.pixelColor(x, image_middle).red() > 180
        assert result.pixelColor(x, image_zone_top + 2) != QtGui.QColor('#ee0088')
        assert result.pixelColor(x, image_zone_bottom - 2) != QtGui.QColor('#ee0088')
        pane.close_project()
        pane.close()
