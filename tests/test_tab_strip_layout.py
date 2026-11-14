"""The inline + must occupy only the space after the last real tab."""
from yomunote.tab_strip import inline_add_position


def test_one_tab_places_plus_alongside_it_not_far_right():
    assert inline_add_position(1100, 185, 180) == 190


def test_multiple_tabs_follow_last_right_edge():
    assert inline_add_position(1100, 500, 495) == 505


def test_overflow_uses_fixed_corner_not_fake_spacer():
    assert inline_add_position(760, 1200, 1200) is None
    assert inline_add_position(760, 680, 680) is None


def test_narrow_and_scroll_offsets_do_not_overlay_tabs():
    assert inline_add_position(0, 0, 0) is None
    assert inline_add_position(760, -5, 2000) is None
