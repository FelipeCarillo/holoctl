"""Tests for holoctl.lib.config — find_project_root, marker auto-migration."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from holoctl.lib.config import (
    find_project_root,
    load_config,
    save_config,
    get_defaults,
)


def _write_legacy_config(root: Path, marker: str) -> None:
    """Plant a legacy `.projctl/` or `.projhub/` workspace under `root`."""
    legacy = root / marker
    legacy.mkdir(parents=True, exist_ok=True)
    config = get_defaults()
    config["project"]["name"] = f"legacy-{marker}"
    (legacy / "config.json").write_text(json.dumps(config), encoding="utf-8")


def test_find_returns_none_when_no_marker(tmp_path: Path):
    assert find_project_root(tmp_path) is None


def test_find_returns_root_when_marker_present(tmp_path: Path):
    config = get_defaults()
    save_config(tmp_path, config)
    assert find_project_root(tmp_path) == tmp_path.resolve()


def test_find_walks_up_to_marker(tmp_path: Path):
    config = get_defaults()
    save_config(tmp_path, config)
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert find_project_root(deep) == tmp_path.resolve()


@pytest.mark.parametrize("legacy_marker", [".projctl", ".projhub"])
def test_legacy_marker_is_recognized(tmp_path: Path, legacy_marker: str):
    """`.projctl/` and `.projhub/` should be discoverable as workspace roots."""
    _write_legacy_config(tmp_path, legacy_marker)
    assert find_project_root(tmp_path) == tmp_path.resolve()


@pytest.mark.parametrize("legacy_marker", [".projctl", ".projhub"])
def test_load_config_migrates_legacy_marker(tmp_path: Path, legacy_marker: str):
    """Reading from a legacy dir should auto-rename it to `.holoctl/`."""
    _write_legacy_config(tmp_path, legacy_marker)
    assert (tmp_path / legacy_marker).exists()
    assert not (tmp_path / ".holoctl").exists()

    load_config(tmp_path)

    assert (tmp_path / ".holoctl").exists()
    assert not (tmp_path / legacy_marker).exists()


def test_load_config_raises_when_no_marker(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path)


def test_save_config_creates_holoctl_dir(tmp_path: Path):
    config = get_defaults()
    config["project"]["name"] = "X"
    save_config(tmp_path, config)
    assert (tmp_path / ".holoctl" / "config.json").exists()
    written = json.loads((tmp_path / ".holoctl" / "config.json").read_text())
    assert written["project"]["name"] == "X"


def test_save_does_not_clobber_existing_holoctl(tmp_path: Path):
    """If `.holoctl/` already exists, legacy dirs are NOT renamed onto it."""
    save_config(tmp_path, get_defaults())
    _write_legacy_config(tmp_path, ".projhub")
    save_config(tmp_path, get_defaults())  # should be a no-op rename
    assert (tmp_path / ".holoctl").exists()
    assert (tmp_path / ".projhub").exists()  # left untouched


def test_load_config_merges_defaults(tmp_path: Path):
    """A partial config in `.holoctl/config.json` should still expose defaults."""
    (tmp_path / ".holoctl").mkdir()
    (tmp_path / ".holoctl" / "config.json").write_text(
        json.dumps({"project": {"name": "P", "prefix": "P"}}),
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg["project"]["name"] == "P"
    assert "statuses" in cfg["board"]
    assert "backlog" in cfg["board"]["statuses"]
