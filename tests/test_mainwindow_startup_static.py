"""Guard against missing MainWindow methods that cause immediate startup crashes.

AST-based so it runs even on systems where PySide6 is not installed.
"""
import ast
from pathlib import Path


def test_mainwindow_has_theme_and_notebook_startup_methods():
    window = Path(__file__).resolve().parents[1] / 'yomunote' / 'window.py'
    tree = ast.parse(window.read_text(encoding='utf-8'))
    klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MainWindow')
    methods = {n.name for n in klass.body if isinstance(n, ast.FunctionDef)}
    required = {'__init__', 'apply_theme', 'set_theme', 'show_notebook',
                'change_tab', 'configure_actions', 'show_preferences',
                'save_project', '_periodic_backup', 'restore_backup'}
    assert required <= methods, f'Missing MainWindow startup methods: {required - methods}'


def test_mainwindow_self_method_calls_are_defined():
    window = Path(__file__).resolve().parents[1] / 'yomunote' / 'window.py'
    tree = ast.parse(window.read_text(encoding='utf-8'))
    klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MainWindow')
    methods = {n.name for n in klass.body if isinstance(n, ast.FunctionDef)}
    qt_inherited = {'menuBar','resize','setCentralWidget','setMinimumSize',
                    'setStatusBar','setWindowTitle','statusBar','windowState',
                    'setAcceptDrops'}
    refs = {n.func.attr for fn in klass.body if isinstance(fn, ast.FunctionDef)
            for n in ast.walk(fn) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
            and n.func.value.id == 'self'}
    unknown = refs - methods - qt_inherited
    assert not unknown, f'MainWindow calls missing methods: {sorted(unknown)}'
