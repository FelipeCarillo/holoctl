from __future__ import annotations
import subprocess
from pathlib import Path


def get_git_info(abs_path: Path) -> dict:
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
