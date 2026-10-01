import os
import subprocess
from typing import List


class GitRepository:
    """
    A temporary Git repository for tests.
    """

    def __init__(self, path_to_root: str) -> None:
        self.path_to_root: str = os.path.realpath(path_to_root)
        self.run(["init", "--quiet", "--initial-branch=main"])
        self.run(["config", "user.name", "Test User"])
        self.run(["config", "user.email", "test@example.com"])
        self.run(["config", "commit.gpgsign", "false"])

    def run(self, arguments: List[str]) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.path_to_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def write_file(self, relative_path: str, content: str) -> str:
        full_path = os.path.join(self.path_to_root, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf8") as file_:
            file_.write(content)
        return full_path

    def read_file(self, relative_path: str) -> str:
        with open(
            os.path.join(self.path_to_root, relative_path), encoding="utf8"
        ) as file_:
            return file_.read()

    def exists(self, relative_path: str) -> bool:
        return os.path.exists(os.path.join(self.path_to_root, relative_path))

    def delete_file(self, relative_path: str) -> None:
        os.remove(os.path.join(self.path_to_root, relative_path))

    def commit_all(self, message: str = "Commit") -> None:
        self.run(["add", "-A"])
        self.run(["commit", "--quiet", "-m", message])

    def get_porcelain_status(self) -> str:
        return self.run(["status", "--porcelain=v1", "--untracked-files=all"])
