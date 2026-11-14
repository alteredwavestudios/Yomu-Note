"""Source and model tests. The Qt GUI tests run when PySide6 is installed."""
from pathlib import Path
import ast

from yomunote.history import UnifiedHistory, CallbackAction, rename_action, reorder_pages_action
from yomunote.importers import blank_page
from yomunote.project import Project

ROOT = Path(__file__).resolve().parents[1] / 'yomunote'


def test_bounded_history_keeps_last_action_and_respects_redo_branch():
    model = {'value': 0}
    history = UnifiedHistory(max_actions=3, max_memory_bytes=450)
    for number in range(1, 6):
        old = model['value']
        history.perform(CallbackAction('Set Value',
            lambda old=old: model.__setitem__('value', old),
            lambda value=number: model.__setitem__('value', value), 200))
    assert model['value'] == 5
    assert history.action_count == 2
    assert history.undo()
    assert model['value'] == 4
    assert history.undo()
    assert model['value'] == 3
    assert not history.undo()
    assert history.redo()
    assert model['value'] == 4
    history.perform(CallbackAction('Branch', lambda: model.__setitem__('value', 4),
                                   lambda: model.__setitem__('value', 6), 200))
    assert not history.can_redo
    assert model['value'] == 6


def test_unified_history_interleaves_notes_marks_and_page_edit():
    data={'notes':'', 'mark':False, 'page':'Old'}
    history=UnifiedHistory()
    history.record_applied(CallbackAction('Edit Notes',
        lambda: data.__setitem__('notes', ''),
        lambda: data.__setitem__('notes', 'text')))
    data['notes']='text'
    history.perform(CallbackAction('Add Highlight',
        lambda: data.__setitem__('mark', False),
        lambda: data.__setitem__('mark', True)))
    history.perform(rename_action('page','p1','Old','New',lambda _id, v: data.__setitem__('page',v)))
    assert data == {'notes':'text','mark':True,'page':'New'}
    history.undo(); assert data['page']=='Old'
    history.undo(); assert data['mark'] is False
    history.undo(); assert data['notes']==''
    history.redo(); history.redo(); history.redo()
    assert data == {'notes':'text','mark':True,'page':'New'}


def test_reorder_is_exact_by_stable_page_id():
    pages={'t':['a','b','c']}
    history=UnifiedHistory()
    command=reorder_pages_action('t',['a','b','c'],['c','a','b'],
                                 lambda tab, ids: pages.__setitem__(tab, ids))
    history.perform(command)
    assert pages['t']==['c','a','b']
    history.undo(); assert pages['t']==['a','b','c']
    history.redo(); assert pages['t']==['c','a','b']


def test_blank_page_requires_no_pdf_asset(tmp_path):
    project = Project(path=tmp_path,name='Test')
    page=blank_page(project)
    assert page['kind']=='blank' and page['source'] is None
    assert page['render_source'] is None and page['id']


def test_wiring_and_no_fixed_height_regression():
    w=(ROOT/'window.py').read_text()
    e=(ROOT/'editor.py').read_text()
    assert 'self.plus_menu.addAction(\'Import File…\'' in w
    assert 'self.plus_menu.addAction(\'Add Blank Page\'' in w
    assert "self.add_page_menu.addAction('Add Blank Page'" in w
    assert 'self.pages_list.blankAt.connect(self.add_blank)' in w
    assert 'line.setAlignment(Qt.AlignmentFlag.AlignLeft' in w
    assert 'self.history.perform(rename_action(' in w
    assert 'self.history.record_applied(reorder_pages_action(' in w
    assert 'self._record_text_edit(p, nid)' in w  # bind each notes document's stable ID
    font_adjust = e.split('    def change_font_size(',1)[1].split('    def clear_formatting(',1)[0]
    assert 'for fragment in block' in font_adjust
    assert 'group.beginEditBlock()' in font_adjust
    assert 'group.endEditBlock()' in font_adjust
    assert 'LineHeightTypes.FixedHeight' not in font_adjust
    assert 'setHtml(' not in font_adjust
    for name in ('window.py','editor.py','notebook.py','history.py'):
        ast.parse((ROOT/name).read_text())
