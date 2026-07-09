import json

from scripts.cursor_store import get_cursor, load_cursors, save_cursors, set_cursor


def test_load_cursors_missing_file_returns_empty_dict(tmp_path):
    path = tmp_path / "cursors.json"
    assert load_cursors(path) == {}


def test_set_cursor_does_not_mutate_input():
    original = {"a": "100"}
    updated = set_cursor(original, "b", "200")
    assert original == {"a": "100"}
    assert updated == {"a": "100", "b": "200"}


def test_get_cursor_unknown_target_returns_none():
    assert get_cursor({"a": "100"}, "unknown") is None


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "cursors.json"
    cursors = set_cursor({}, "frontend-b2c", "1717000000.000100")
    save_cursors(path, cursors)

    loaded = load_cursors(path)

    assert loaded == {"frontend-b2c": "1717000000.000100"}
    assert json.loads(path.read_text()) == {"frontend-b2c": "1717000000.000100"}
