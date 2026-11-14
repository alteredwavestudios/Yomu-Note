"""Portable, explicit per-paragraph overrides: tests need no Qt GUI."""
from yomunote.notes_spacing import add_spacing_metadata, split_spacing_metadata
import pytest


def test_explicit_zero_gap_survives_html_roundtrip():
    source = '<html><body><p>Some text</p></body></html>'
    stored = add_spacing_metadata(source, {
        0: {'after_pt': 0.0, 'before_pt': 8.0, 'line': 1.15},
        9: {'after_pt': 12.25},
    })
    assert 'YOMU_SPACING_V1:' in stored
    html, overrides = split_spacing_metadata(stored)
    assert html.strip() == source
    assert overrides[0]['after_pt'] == 0
    assert overrides[9]['after_pt'] == 12.25


def test_old_html_stays_identical_without_new_metadata():
    source = '<html><body><p>Old notebook</p></body></html>'
    assert add_spacing_metadata(source, {}) == source
    assert split_spacing_metadata(source) == (source, {})


def test_malformed_metadata_preserves_notes_text():
    html, overrides = split_spacing_metadata(
        '<p>Read this</p><!-- YOMU_SPACING_V1:SGVsbG8 -->')
    assert '<p>Read this</p>' in html
    assert overrides == {}


@pytest.mark.parametrize('override', [
    {0: {'after_pt': -1}},
    {0: {'before_pt': 300}},
    {0: {'line': 0.5}},
    {0: {'after_pt': float('nan')}},
    {0: {'after_pt': True}},
    {-1: {'after_pt': 0}},
    {0: {'unrecognised': 3}},
])
def test_bad_overrides_rejected(override):
    with pytest.raises(ValueError):
        add_spacing_metadata('<p>Text</p>', override)
