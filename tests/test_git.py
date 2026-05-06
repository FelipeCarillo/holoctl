"""Tests for holoctl.lib.git — read_git_fast() reads .git/ without subprocess."""
from __future__ import annotations
from pathlib import Path

from holoctl.lib.git import read_git_fast


def _init_git_dir(repo: Path, *, head: str, config: str = "", refs: dict | None = None,
                   packed_refs: str | None = None) -> None:
    """Plant a minimal `.git/` for read_git_fast tests."""
    git = repo / ".git"
    git.mkdir(parents=True, exist_ok=True)
    (git / "HEAD").write_text(head, encoding="utf-8")
    if config:
        (git / "config").write_text(config, encoding="utf-8")
    for ref_path, sha in (refs or {}).items():
        target = git / ref_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(sha, encoding="utf-8")
    if packed_refs is not None:
        (git / "packed-refs").write_text(packed_refs, encoding="utf-8")


def test_returns_not_git_when_no_git_dir(tmp_path: Path):
    assert read_git_fast(tmp_path)["isGit"] is False


def test_returns_not_git_when_path_missing(tmp_path: Path):
    assert read_git_fast(tmp_path / "nope")["isGit"] is False


def test_reads_branch_from_loose_ref(tmp_path: Path):
    _init_git_dir(
        tmp_path,
        head="ref: refs/heads/main\n",
        refs={"refs/heads/main": "abc1234567890abcdef1234567890abcdef1234\n"},
    )
    info = read_git_fast(tmp_path)
    assert info["isGit"] is True
    assert info["branch"] == "main"
    assert info["commitHash"] == "abc1234"


def test_reads_branch_from_packed_refs_when_loose_missing(tmp_path: Path):
    _init_git_dir(
        tmp_path,
        head="ref: refs/heads/develop\n",
        packed_refs=(
            "# pack-refs with: peeled fully-peeled sorted\n"
            "deadbee0000000000000000000000000000beef refs/heads/develop\n"
            "1234567890abcdef1234567890abcdef12345678 refs/tags/v1.0\n"
            "^abcdef1234567890abcdef1234567890abcdef12\n"
        ),
    )
    info = read_git_fast(tmp_path)
    assert info["branch"] == "develop"
    assert info["commitHash"] == "deadbee"


def test_detached_head_uses_sha(tmp_path: Path):
    sha = "facefeed00000000000000000000000000000000\n"
    _init_git_dir(tmp_path, head=sha)
    info = read_git_fast(tmp_path)
    assert info["branch"] == "HEAD"
    assert info["commitHash"] == "facefee"


def test_reads_remote_url(tmp_path: Path):
    _init_git_dir(
        tmp_path,
        head="ref: refs/heads/main\n",
        refs={"refs/heads/main": "abc1234567890abcdef1234567890abcdef1234\n"},
        config=(
            "[core]\n"
            "\trepositoryformatversion = 0\n"
            '[remote "origin"]\n'
            "\turl = git@github.com:user/repo.git\n"
            "\tfetch = +refs/heads/*:refs/remotes/origin/*\n"
            '[remote "upstream"]\n'
            "\turl = git@github.com:other/repo.git\n"
        ),
    )
    info = read_git_fast(tmp_path)
    assert info["remote"] == "git@github.com:user/repo.git"


def test_no_remote_when_origin_missing(tmp_path: Path):
    _init_git_dir(
        tmp_path,
        head="ref: refs/heads/main\n",
        refs={"refs/heads/main": "abc1234\n"},
        config="[core]\n\trepositoryformatversion = 0\n",
    )
    assert read_git_fast(tmp_path)["remote"] is None


def test_does_not_include_dirty_field(tmp_path: Path):
    """The whole point: no `git status` call, so no dirty info."""
    _init_git_dir(
        tmp_path,
        head="ref: refs/heads/main\n",
        refs={"refs/heads/main": "abc1234\n"},
    )
    info = read_git_fast(tmp_path)
    assert "dirty" not in info
    assert "lastCommit" not in info
    assert "commitDate" not in info


def test_handles_gitfile_pointer(tmp_path: Path):
    """A `.git` file (worktree/submodule) points at a real gitdir elsewhere."""
    real = tmp_path / "actual_gitdir"
    real.mkdir()
    (real / "HEAD").write_text("ref: refs/heads/feature\n", encoding="utf-8")
    refs_dir = real / "refs" / "heads"
    refs_dir.mkdir(parents=True)
    (refs_dir / "feature").write_text("cafef00d000000000000000000000000\n", encoding="utf-8")

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {real}\n", encoding="utf-8")

    info = read_git_fast(worktree)
    assert info["isGit"] is True
    assert info["branch"] == "feature"
    assert info["commitHash"] == "cafef00"
