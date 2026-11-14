"""Qt-free guard against the v0.7.1 deleted-status-widget regression.

MainWindow may put progress widgets into its status bar, but must never
replace that bar afterwards: Qt deletes its old child widgets and leaves
Python's references pointing at destroyed QLabel/QProgressBar objects.
"""
import ast
from pathlib import Path


def test_notebook_status_bar_is_created_once_before_progress_widgets():
    source = Path(__file__).resolve().parents[1] / 'yomunote' / 'window.py'
    module = ast.parse(source.read_text(encoding='utf-8'))
    klass = next(node for node in module.body
                 if isinstance(node, ast.ClassDef) and node.name == 'MainWindow')
    constructor = next(node for node in klass.body
                       if isinstance(node, ast.FunctionDef) and node.name == '__init__')
    calls = [node for node in ast.walk(constructor)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    installations = [node for node in calls if node.func.attr == 'setStatusBar']
    permanents = [node for node in calls if node.func.attr == 'addPermanentWidget']
    assert len(installations) == 1, 'Replacing QStatusBar destroys its permanent widgets'
    # v0.7.2 moves the progress display into the persistent header.
    assert len(permanents) == 0
    assert 'header_layout.addWidget(notebook_header' in source.read_text(encoding='utf-8')


def test_progress_checkbox_painter_preserves_native_hit_testing_and_theme():
    source = (Path(__file__).resolve().parents[1] /
              'yomunote' / 'page_groups_ui.py').read_text(encoding='utf-8')
    # Paint a themed overlay at Qt's own visual hit rectangle, not a new
    # interactive widget that would change click handling or Undo semantics.
    assert 'SE_ItemViewItemCheckIndicator' in source
    assert 'QPalette.ColorRole.Base' in source
    assert 'self.accent if active else fill' in source
    assert 'Qt.CheckState.PartiallyChecked' in source
    assert 'self.readToggled.emit(' in source
