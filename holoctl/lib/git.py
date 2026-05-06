from __future__ import annotations
import subprocess
from pathlib import Path


def read_git_fast(abs_path: Path) -> dict:
    """Read git metadata by parsing `.git/` directly. **No subprocess.**

    Returns the same shape as `get_git_info()` but with `lastCommit`,
    `commitDate`, and `dirty` left out — those need real git work
    (object decompression, working-tree scan) and are the slow path on
    Windows + corporate AV. Use `get_git_info()` when you actually need
    them.

    Used by `discover_repos()` so home/board/sidebar pages don't pay the
    subprocess cost. The dashboard's Repos tab and `holoctl repo info`
    still call the full version on demand.
    """
    if not abs_path.exists():
        return {"isGit": False}

    git_dir = abs_path / ".git"
    if not git_dir.exists():
        return {"isGit": False}

    # `.git` is a file in worktrees and submodules: `gitdir: <path>`.
    if git_dir.is_file():
        try:
            content = git_dir.read_text(encoding="utf-8").strip()
        except OSError:
            return {"isGit": False}
        if not content.startswith("gitdir:"):
            return {"isGit": False}
        relocated = (abs_path / content.split(":", 1)[1].strip()).resolve()
        if not relocated.is_dir():
            return {"isGit": False}
        git_dir = relocated

    branch = "HEAD"
    commit_hash = ""
    head_path = git_dir / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except OSError:
        head = ""

    if head.startswith("ref: "):
        ref = head[5:].strip()
        # Branch name is the last segment of the ref.
        branch = ref.split("/")[-1] if "/" in ref else ref
        ref_file = git_dir / ref
        try:
            commit_hash = ref_file.read_text(encoding="utf-8").strip()[:7]
        except OSError:
            commit_hash = _lookup_packed_ref(git_dir, ref)
    elif head:
        # Detached HEAD — file contains the SHA itself.
        commit_hash = head[:7]

    remote = _read_remote_url(git_dir)

    return {
        "isGit": True,
        "branch": branch or "HEAD",
        "commitHash": commit_hash,
        "remote": remote,
    }


def _lookup_packed_ref(git_dir: Path, ref: str) -> str:
    packed = git_dir / "packed-refs"
    try:
        content = packed.read_text(encoding="utf-8")
    except OSError:
        return ""
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("^"):
            continue
        parts = line.split(" ", 1)
        if len(parts) == 2 and parts[1] == ref:
            return parts[0][:7]
    return ""


def _read_remote_url(git_dir: Path) -> str | None:
    config = git_dir / "config"
    try:
        content = config.read_text(encoding="utf-8")
    except OSError:
        return None
    in_origin = False
    for raw in content.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_origin = line == '[remote "origin"]'
            continue
        if in_origin and "=" in line:
            key, _, val = line.partition("=")
            if key.strip() == "url":
                return val.strip() or None
    return None


def get_git_info(abs_path: Path) -> dict:
    """Full git metadata, including `dirty` and the last commit message.

    Spawns `git` subprocesses (5 of them). On Windows + corporate AV each
    spawn can take 100-300ms, so prefer `read_git_fast()` for hot paths
    (dashboard home/board, sidebar) and only call this on the explicit
    Repos tab or `holoctl repo info`.
    """
    if not abs_path.exists():
        return {"isGit": False}

    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=abs_path, capture_output=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"isGit": False}

    def run(cmd: list[str]) -> str:
        try:
            return subprocess.run(
                cmd, cwd=abs_path, capture_output=True, text=True
            ).stdout.strip()
        except Exception:
            return ""

    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    commit_hash = run(["git", "log", "-1", "--pretty=format:%H"])[:7]
    commit_msg = run(["git", "log", "-1", "--pretty=format:%s"])
    commit_date = run(["git", "log", "-1", "--pretty=format:%cd", "--date=short"])
    dirty = bool(run(["git", "status", "--porcelain"]))
    remote = run(["git", "remote", "get-url", "origin"])

    return {
        "isGit": True,
        "branch": branch or "HEAD",
        "commitHash": commit_hash,
        "lastCommit": commit_msg,
        "commitDate": commit_date,
        "dirty": dirty,
        "remote": remote or None,
    }
