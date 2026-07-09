import pytest

from scripts.load_targets import load_targets

VALID_YAML = """
targets:
  - name: frontend-b2c
    slack_channel_id: C123
    repo: adadot/frontend-b2c
    branch: main
"""

VALID_YAML_WITH_CAP = """
targets:
  - name: frontend-b2c
    slack_channel_id: C123
    repo: adadot/frontend-b2c
    branch: main
    max_errors_per_run: 2
"""

MISSING_FIELD_YAML = """
targets:
  - name: frontend-b2c
    slack_channel_id: C123
    branch: main
"""

PLACEHOLDER_YAML = """
targets:
  - name: frontend-b2c
    slack_channel_id: REPLACE_ME_SLACK_CHANNEL_ID
    repo: adadot/frontend-b2c
    branch: main
"""

EMPTY_YAML = "targets: []\n"


def _write(tmp_path, content):
    path = tmp_path / "targets.yaml"
    path.write_text(content)
    return path


def test_load_targets_applies_default_cap(tmp_path):
    path = _write(tmp_path, VALID_YAML)
    targets = load_targets(path)
    assert targets[0]["max_errors_per_run"] == 5


def test_load_targets_respects_explicit_cap(tmp_path):
    path = _write(tmp_path, VALID_YAML_WITH_CAP)
    targets = load_targets(path)
    assert targets[0]["max_errors_per_run"] == 2


def test_load_targets_missing_required_field_raises(tmp_path):
    path = _write(tmp_path, MISSING_FIELD_YAML)
    with pytest.raises(ValueError, match="repo"):
        load_targets(path)


def test_load_targets_placeholder_channel_id_raises(tmp_path):
    path = _write(tmp_path, PLACEHOLDER_YAML)
    with pytest.raises(ValueError, match="placeholder"):
        load_targets(path)


def test_load_targets_empty_raises(tmp_path):
    path = _write(tmp_path, EMPTY_YAML)
    with pytest.raises(ValueError, match="No targets"):
        load_targets(path)
