"""Start Yomu Note. Compatible with macOS Apple Silicon, Windows and Linux."""
from __future__ import annotations
import sys
from pathlib import Path


def _verify_frozen_runtime():
    """Non-interactive packaged-app self-test; no user notebook is opened.

    Windows' GUI bootloader may hide Python stderr, so write the failure to
    the caller-provided disposable marker path rather than showing a dialog.
    This MUST run before normal PySide6 and MainWindow startup imports.
    """
    import json
    import sqlite3
    import traceback

    marker = Path(sys.argv[sys.argv.index('--yomu-bundle-smoke') + 1])
    try:
        if not getattr(sys, 'frozen', False):
            raise RuntimeError('Bundle check requires the packaged executable')
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE smoke_check (id INTEGER NOT NULL)')
            db.execute('INSERT INTO smoke_check VALUES (42)')
            assert db.execute('SELECT id FROM smoke_check').fetchone()[0] == 42
        # Verify the actual imports needed for launching the application.
        import pypdfium2
        from PIL import Image
        from PySide6.QtCore import QCoreApplication
        from yomunote.window import MainWindow
        marker.write_text(json.dumps({'status': 'ok',
            'sqlite_version': sqlite3.sqlite_version,
            'window_module': MainWindow.__module__}), encoding='utf-8')
    except BaseException:
        marker.with_name(marker.name + '.error.txt').write_text(
            traceback.format_exc(), encoding='utf-8')
        return 1
    return 0


if __name__ == '__main__' and '--yomu-bundle-smoke' in sys.argv:
    sys.exit(_verify_frozen_runtime())

from PySide6.QtGui import QIcon, QPixmapCache, QFont, QFontDatabase
from PySide6.QtCore import QThreadPool, qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from yomunote import __version__
from yomunote.window import MainWindow


def _font_warning_filter(message_type, context, message):
    """Hide one repetitive Qt bitmap-font metrics warning on affected Macs.

    It arises inside Qt font handling, not in the Yomu document renderer.
    Preserve all unrelated Qt diagnostics so actual problems stay visible.
    Qt's Python message-handler lifetime is the lifetime of this module.
    """
    if 'Failed to compute left/right minimum bearings for "GB18030 Bitmap"' in message:
        return
    print(message, file=sys.stderr)



def main():
    qInstallMessageHandler(_font_warning_filter)
    app = QApplication(sys.argv)
    app.setApplicationName('Yomu Note')
    app.setApplicationVersion(__version__)
    app.setOrganizationName('Yomu Note')
    app.setStyle('Fusion')
    # Avoid retaining unlimited images in Qt's global implicit pixmap cache.
    # Thumbnail widgets own at most 20 icon pixmaps; inactive tabs release them.
    QPixmapCache.setCacheLimit(4096)  # KB, separate from active page's memory
    # 2 GB RAM target: never run a large Office conversion and many PDF decodes in parallel.
    QThreadPool.globalInstance().setMaxThreadCount(2)
    resources = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    # Register optional locally downloaded OFL fonts before creating widgets.
    # Downloading only happens when a user runs fetch_fonts.py; Yomu never
    # uses the internet at runtime, and bundled builds remain fully offline.
    for font_path in sorted((resources / 'assets' / 'fonts').rglob('*.ttf')):
        if QFontDatabase.addApplicationFont(str(font_path)) < 0:
            print(f'Could not load optional font: {font_path.name}', file=sys.stderr)
    families = set(QFontDatabase.families())
    # The global UI font applies to buttons, menus, tabs, labels, dialogs,
    # and controls, NOT the notes document's separately configured font.
    # Keep graceful fallbacks for running from source without downloaded fonts.
    if 'Montserrat' in families:
        app.setFont(QFont('Montserrat', 11))
    elif 'Nunito' in families:
        app.setFont(QFont('Nunito', 11))
    icon = resources / 'assets' / 'icon.png'
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
