"""
Run one project action at a time and keep its output for the web UI.

The runner starts the process without a shell, in the project root. A
reader thread collects the combined stdout and stderr line by line. When
the process exits, the runner calls on_finished, which rebuilds the
traceability index and returns a build error or None. Only then does the
runner mark the run as finished, so that a client that reloads on the
finished event sees the new results.
"""

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from strictdoc.features.project_actions.project_action import ProjectAction

MAX_BUFFERED_LINES = 10000
CANCEL_GRACE_PERIOD_SECONDS = 5.0


class ProjectActionRunState:
    RUNNING = "running"
    REBUILDING = "rebuilding"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ERROR = "error"

    FINISHED = (SUCCEEDED, FAILED, CANCELLED, ERROR)


class ProjectActionBusyError(Exception):
    pass


@dataclass
class ProjectActionRun:
    run_id: int
    action: ProjectAction
    argv: List[str]
    started_at: float
    state: str = ProjectActionRunState.RUNNING
    finished_at: Optional[float] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
    # Lines are numbered from the start of the run. When the buffer is full,
    # the oldest lines are dropped and dropped_lines counts them.
    lines: List[str] = field(default_factory=list)
    dropped_lines: int = 0
    # Paths relative to the project root, in POSIX form.
    output_files: List[str] = field(default_factory=list)
    cancel_requested: bool = False

    def is_finished(self) -> bool:
        return self.state in ProjectActionRunState.FINISHED

    def get_line_count(self) -> int:
        return self.dropped_lines + len(self.lines)

    def get_duration_seconds(self) -> float:
        end = self.finished_at if self.finished_at is not None else time.time()
        return end - self.started_at


class ProjectActionRunner:
    def __init__(
        self,
        *,
        project_root: str,
        on_finished: Callable[[], Optional[str]],
    ) -> None:
        self.project_root: Path = Path(project_root).resolve()
        self.on_finished: Callable[[], Optional[str]] = on_finished
        self.last_run: Optional[ProjectActionRun] = None
        self._process: Optional[subprocess.Popen[str]] = None
        self._condition = threading.Condition()
        self._next_run_id = 1

    def start(self, action: ProjectAction, argv: List[str]) -> ProjectActionRun:
        with self._condition:
            if self.last_run is not None and not self.last_run.is_finished():
                raise ProjectActionBusyError(
                    f"The action '{self.last_run.action.title}' is still "
                    "running."
                )
            run = ProjectActionRun(
                run_id=self._next_run_id,
                action=action,
                argv=argv,
                started_at=time.time(),
            )
            self._next_run_id += 1
            self.last_run = run
            output_mtimes = self._snapshot_outputs(action)
            try:
                self._process = subprocess.Popen(
                    argv,
                    cwd=self.project_root,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                    # A new session lets cancel() stop the whole process
                    # group, e.g. the Python process that "uv run" starts.
                    start_new_session=sys.platform != "win32",
                )
            except OSError as os_error_:
                run.state = ProjectActionRunState.ERROR
                run.error_message = str(os_error_)
                run.finished_at = time.time()
                self._condition.notify_all()
                return run
            thread = threading.Thread(
                target=self._read_output,
                args=(run, self._process, output_mtimes),
                daemon=True,
            )
            thread.start()
            return run

    def cancel(self) -> None:
        with self._condition:
            run = self.last_run
            process = self._process
            if run is None or run.is_finished() or process is None:
                return
            if run.state != ProjectActionRunState.RUNNING:
                return
            run.cancel_requested = True
        self._signal(process, signal.SIGTERM)
        killer = threading.Timer(
            CANCEL_GRACE_PERIOD_SECONDS,
            self._kill_if_alive,
            args=(process,),
        )
        killer.daemon = True
        killer.start()

    def wait_for_lines(
        self, run_id: int, offset: int, timeout: float
    ) -> Tuple[List[str], int, bool]:
        """
        Return the lines from offset, the next offset and whether the run is
        finished. Block up to timeout seconds while there is nothing new.
        """

        with self._condition:
            run = self.last_run
            if run is None or run.run_id != run_id:
                return [], offset, True
            if offset >= run.get_line_count() and not run.is_finished():
                self._condition.wait(timeout)
            start = max(offset, run.dropped_lines)
            lines = run.lines[start - run.dropped_lines :]
            return list(lines), run.get_line_count(), run.is_finished()

    def is_output_file(self, relative_path: str) -> bool:
        run = self.last_run
        return run is not None and relative_path in run.output_files

    def _read_output(
        self,
        run: ProjectActionRun,
        process: "subprocess.Popen[str]",
        output_mtimes: Dict[str, float],
    ) -> None:
        assert process.stdout is not None
        for line_ in process.stdout:
            with self._condition:
                run.lines.append(line_.rstrip("\r\n"))
                if len(run.lines) > MAX_BUFFERED_LINES:
                    del run.lines[0]
                    run.dropped_lines += 1
                self._condition.notify_all()
        exit_code = process.wait()
        with self._condition:
            run.exit_code = exit_code
            run.state = ProjectActionRunState.REBUILDING
            self._condition.notify_all()
        run.output_files = self._changed_outputs(run.action, output_mtimes)
        rebuild_error: Optional[str] = None
        try:
            build_error = self.on_finished()
        except Exception as exception_:  # noqa: BLE001
            build_error = str(exception_)
        if build_error is not None:
            rebuild_error = f"Rebuild failed: {build_error}"
        with self._condition:
            if run.cancel_requested:
                run.state = ProjectActionRunState.CANCELLED
            elif exit_code == 0 and rebuild_error is None:
                run.state = ProjectActionRunState.SUCCEEDED
            else:
                run.state = ProjectActionRunState.FAILED
            run.error_message = rebuild_error
            run.finished_at = time.time()
            self._process = None
            self._condition.notify_all()

    def _snapshot_outputs(self, action: ProjectAction) -> Dict[str, float]:
        return {
            relative_path_: path_.stat().st_mtime
            for relative_path_, path_ in self._glob_outputs(action)
        }

    def _changed_outputs(
        self, action: ProjectAction, output_mtimes: Dict[str, float]
    ) -> List[str]:
        changed: List[str] = []
        for relative_path_, path_ in self._glob_outputs(action):
            previous_mtime = output_mtimes.get(relative_path_)
            if previous_mtime is None or path_.stat().st_mtime > previous_mtime:
                changed.append(relative_path_)
        return sorted(changed)

    def _glob_outputs(self, action: ProjectAction) -> List[Tuple[str, Path]]:
        result: Dict[str, Path] = {}
        for pattern_ in action.outputs:
            for path_ in self.project_root.glob(pattern_):
                resolved_path = path_.resolve()
                if not resolved_path.is_file():
                    continue
                if not resolved_path.is_relative_to(self.project_root):
                    continue
                relative_path = resolved_path.relative_to(
                    self.project_root
                ).as_posix()
                result[relative_path] = resolved_path
        return sorted(result.items())

    @staticmethod
    def _signal(process: "subprocess.Popen[str]", signal_number: int) -> None:
        if process.poll() is not None:
            return
        if sys.platform == "win32":  # pragma: no cover
            process.kill()
            return
        try:
            os.killpg(process.pid, signal_number)
        except ProcessLookupError:
            pass

    @classmethod
    def _kill_if_alive(cls, process: "subprocess.Popen[str]") -> None:
        cls._signal(process, signal.SIGKILL)
