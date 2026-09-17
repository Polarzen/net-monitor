from dataclasses import replace
import json
import pytest

from net_monitor.ui.preferences import PreferencesStore, UiPreferences
from net_monitor.ui.window_geometry import Rect, fit_rect, place_card, screen_for


@pytest.mark.parametrize('data', [None, [], 'bad', {'version': 99}, {'mode': 'invalid'},
    {'micro_on_top': 'false'}, {'micro_position': [True, 7]}, {'micro_position': [10**40, 0]}])
def test_preferences_corruption_safe_defaults(data):
    assert UiPreferences.from_mapping(data) == UiPreferences()


def test_preferences_allow_negative_logical_positions_and_only_ui_fields(tmp_path):
    store = PreferencesStore(tmp_path / 'ui.json')
    prefs = UiPreferences('compact', (-1800, 22), (5, 6), True)
    assert store.save(prefs)
    assert store.load() == prefs
    data = json.loads(store.path.read_text())
    assert set(data) == {'version', 'mode', 'micro_position', 'compact_position', 'micro_on_top'}
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.parametrize('content', ['{broken', 'x'*9000, '{"mode":"compact", "micro_position":null}'])
def test_load_invalid_or_partial_json(tmp_path, content):
    path = tmp_path / 'ui.json'
    path.write_text(content)
    loaded = PreferencesStore(path).load()
    assert loaded.mode == ('compact' if content.startswith('{"mode"') else 'micro')


def test_settings_io_failure_does_not_crash(tmp_path):
    path = tmp_path / 'file'
    path.write_text('not a directory')
    store = PreferencesStore(path / 'ui.json')
    assert store.load() == UiPreferences()
    assert not store.save(UiPreferences())


def test_screen_recovery_after_disconnect_and_negative_coordinates():
    left = Rect(-1920, 0, 1920, 1040)
    right = Rect(0, 0, 1920, 1040)
    widget = Rect(-1800, 50, 112, 72)
    assert fit_rect(widget, (left, right)) == widget
    restored = fit_rect(widget, (right,))
    assert right.contains(restored)
    assert restored.x == 0


def test_snap_and_layout_direction_are_based_on_available_area():
    screen = Rect(-1600, -100, 1600, 1000)
    widget = fit_rect(Rect(-119, 10, 112, 72), (screen,), snap=12)
    assert widget.right == 0
    card = place_card(widget, (360, 420), (screen,))
    assert card.right <= widget.x
    assert screen.contains(card)


def test_small_screen_card_dimensions_are_bounded():
    screen = Rect(0, 0, 300, 250)
    card = place_card(Rect(100, 50, 112, 72), (360, 480), (screen,))
    assert screen.contains(card)
    assert (card.width, card.height) == (300, 250)


def test_no_screen_does_not_invent_a_desktop():
    with pytest.raises(ValueError):
        screen_for(Rect(0, 0, 112, 72), ())
