"""v0.8.1a: hostile-file handling and beginner-facing source checks (no Qt).

These tests intentionally damage COPIES of notebooks, never real user files.
They test that untrusted shared material cannot silently bypass metadata size
checks or leave partial imported tabs behind.
"""
from __future__ import annotations

import ast
import json
import sqlite3
from pathlib import Path

import pytest

from yomunote.notebook import Notebook
from yomunote.tab_exchange import inspect_notebook, stage_import, export_tabs


def create_shared(tmp_path):
    """Make a tiny real SQLite notebook with two tabs and independent assets."""
    source = Notebook.create(tmp_path, 'Source')
    ids = [source.active_id, source.add_tab('Another week')]
    for index, tabid in enumerate(ids):
        project = source.project(tabid)
        filename = f'originals/week{index + 1}.pdf'
        project.asset_path(filename).write_bytes(f'%PDF week {index+1}'.encode())
        project.pages = [{'id': f'page-{index}', 'title': 'Reading',
                          'source': filename, 'render_source': filename,
                          'source_page': 1, 'kind': 'pdf'}]
        project.save()
    source.save()
    return source, ids


def test_false_asset_size_is_rejected_before_staged_copy(tmp_path, monkeypatch):
    source, ids = create_shared(tmp_path)
    receiver = Notebook.create(tmp_path / 'receiver', 'My notes')
    try:
        import yomunote.tab_exchange as exchange
        attempted = []
        monkeypatch.setattr(exchange, '_stream_row',
                            lambda *args, **kwargs: attempted.append(True))
        with sqlite3.connect(source.path) as conn:
            conn.execute('UPDATE files SET size=12345 WHERE path=?',
                         (f'tabs/{ids[1]}/originals/week2.pdf',))
        with pytest.raises(ValueError, match='missing required asset'):
            stage_import(source.path, ids, receiver.workspace)
        assert attempted == []  # preflight runs BEFORE copying tab 1
        assert len(receiver.tabs) == 1
        assert not list(receiver.workspace.glob('.tab-exchange-*'))
    finally:
        receiver.close()
        source.close()


def test_bogus_project_metadata_length_rejected_on_inspection(tmp_path):
    source, ids = create_shared(tmp_path)
    try:
        with sqlite3.connect(source.path) as conn:
            conn.execute('UPDATE files SET size=size+1 WHERE path=?',
                         (f'tabs/{ids[0]}/project.json',))
        with pytest.raises(ValueError, match='metadata'):
            inspect_notebook(source.path)
    finally:
        source.close()


def test_export_with_false_size_leaves_no_output(tmp_path):
    source, ids = create_shared(tmp_path)
    try:
        with sqlite3.connect(source.path) as conn:
            conn.execute('UPDATE files SET size=size-1 WHERE path=?',
                         (f'tabs/{ids[0]}/originals/week1.pdf',))
        target = tmp_path / 'Shared.yomunote'
        with pytest.raises(ValueError, match='missing required asset'):
            export_tabs(source.path, target, [ids[0]])
        assert not target.exists()
        assert not list(tmp_path.glob('.*.tmp'))
    finally:
        source.close()


def test_notebook_loader_rejects_dishonest_sqlite_blob_size(tmp_path):
    source, ids = create_shared(tmp_path)
    path = source.path
    source.close()
    with sqlite3.connect(path) as conn:
        conn.execute('UPDATE files SET size=size+1 WHERE path=?',
                     (f'tabs/{ids[0]}/originals/week1.pdf',))
    with pytest.raises(ValueError, match='extraction limits'):
        Notebook.load(path)


def test_notebook_loader_rejects_negative_timestamps(tmp_path):
    source, ids = create_shared(tmp_path)
    path = source.path
    source.close()
    with sqlite3.connect(path) as conn:
        conn.execute('UPDATE files SET mtime_ns=-1 WHERE path=?',
                     (f'tabs/{ids[0]}/originals/week1.pdf',))
    with pytest.raises(ValueError, match='timestamp'):
        Notebook.load(path)


def test_manifest_size_guard_runs_before_fetch(tmp_path, monkeypatch):
    source, ids = create_shared(tmp_path)
    path = source.path
    source.close()
    import yomunote.tab_exchange as exchange
    import yomunote.notebook as notebook
    # Small caps simulate a huge hostile manifest without allocating 32 MiB.
    monkeypatch.setattr(exchange, 'MANIFEST_MAX', 64)
    monkeypatch.setattr(notebook, 'MAX_MANIFEST_BYTES', 64)
    with pytest.raises(ValueError, match='manifest'):
        inspect_notebook(path)
    with pytest.raises(ValueError, match='manifest'):
        Notebook.load(path)


def test_important_classes_have_beginner_help_in_source():
    root = Path(__file__).resolve().parents[1] / 'yomunote'
    for module_name, class_name in [
        ('notebook', 'Notebook'), ('project', 'Project'),
        ('window', 'MainWindow'), ('window', 'ProjectPane'),
        ('window', 'ImageCanvas'), ('tab_exchange_dialog', 'TabExchangeDialog'),
        ('tasks', 'Task'), ('editor', 'NotesEditor'),
    ]:
        tree = ast.parse((root / f'{module_name}.py').read_text('utf-8'))
        node = next(item for item in tree.body
                    if isinstance(item, ast.ClassDef) and item.name == class_name)
        assert len(ast.get_docstring(node) or '') >= 60


def test_export_verifies_sqlite_pragma_result():
    """Don't accidentally regress to execute() without reading the answer."""
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'yomunote'
                      / 'tab_exchange.py').read_text('utf-8'))
    export = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == 'export_tabs')
    src = ast.get_source_segment((Path(__file__).resolve().parents[1] /
                                  'yomunote' / 'tab_exchange.py').read_text('utf-8'), export)
    assert "PRAGMA quick_check').fetchone()" in src
    assert "integrity != ('ok',)" in src
