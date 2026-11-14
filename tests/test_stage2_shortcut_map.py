"""Non-GUI sanity tests for the portable Google Docs editor shortcut map."""
import yomunote.platform_shortcuts as keyboard


def test_windows_google_docs_link_shortcuts(monkeypatch):
    monkeypatch.setattr(keyboard, 'IS_MAC', False)
    assert keyboard.docs_shortcut('web_link') == 'Ctrl+Alt+K'
    assert keyboard.docs_shortcut('page_link') == 'Ctrl+K'
    assert keyboard.docs_shortcut('larger_font') == 'Ctrl+Shift+.'
    assert keyboard.docs_shortcut('smaller_font') == 'Ctrl+Shift+,'


def test_mac_google_docs_link_shortcuts(monkeypatch):
    monkeypatch.setattr(keyboard, 'IS_MAC', True)
    assert keyboard.docs_shortcut('web_link') == '⌘⌥K'
    assert keyboard.docs_shortcut('page_link') == '⌘K'
    assert keyboard.docs_shortcut('bold') == '⌘B'
    assert keyboard.docs_shortcut('notes_zoom_reset') == '⌘0'
