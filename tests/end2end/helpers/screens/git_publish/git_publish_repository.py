import os
import shutil
import subprocess
from typing import List


class GitPublishRepository:
    """
    A temporary Git repository for GIT_PUBLISH end-to-end tests.
    """

    def __init__(self, path_to_root: str) -> None:
        # realpath because macOS symlinks /var to /private/var.
        self.path_to_root: str = os.path.realpath(path_to_root)

    def init(self) -> None:
        self.run(["init", "--quiet"])
        self.run(["config", "user.name", "Your Name"])
        self.run(["config", "user.email", "you@example.com"])

    def copy_file(self, path_to_source_file: str, relative_path: str) -> None:
        path_to_destination = os.path.join(self.path_to_root, relative_path)
        os.makedirs(os.path.dirname(path_to_destination), exist_ok=True)
        shutil.copyfile(path_to_source_file, path_to_destination)

    def commit_all(self, message: str) -> None:
        self.run(["add", "-A"])
        self.run(["commit", "--quiet", "-m", message])

    def run(self, arguments: List[str]) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.path_to_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def get_porcelain_status(self, paths: List[str]) -> str:
        return self.run(
            ["status", "--porcelain=v1", "--untracked-files=all", "--", *paths]
        )

    def exists(self, relative_path: str) -> bool:
        return os.path.exists(os.path.join(self.path_to_root, relative_path))
