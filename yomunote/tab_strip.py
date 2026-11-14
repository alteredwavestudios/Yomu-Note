"""Qt-independent geometry for the trailing Add Tab button.

The overflow corner remains a constant 38x34 pixels. An inline button is a
QTabWidget child, not a dynamically stretched corner or a child of a tab bar
that may be only as wide as the tabs.
"""


def inline_add_position(widget_width: int, last_tab_right: int,
                        total_tab_width: int, *,
                        corner_width: int = 38, button_width: int = 32,
                        gap: int = 5, margin: int = 7) -> int | None:
    """Return inline button's x, or None if the strip needs overflow mode.

    last_tab_right is already mapped into QTabWidget coordinates and may be
    negative when the native QTabBar has been scrolled. total_tab_width never
    includes the flexible empty area or the corner widget.
    """
    available = max(0, int(widget_width) - int(corner_width) - int(margin))
    x = int(last_tab_right) + int(gap)
    if x < 0 or x + button_width > available:
        return None
    if int(total_tab_width) + gap + button_width > available:
        return None
    return x
