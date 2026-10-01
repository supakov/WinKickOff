"""The single crossing point between server threads and the thread that owns the workspace.

With a window, tkinter widgets and the open Profile live on the main thread: a tool submits a closure, the window
pumps the queue from an after() timer and runs the closure there. A read closure only takes a snapshot (a deep copy
of the profile); a write closure performs the whole change and returns its result. Without a window (stdio) the
InlineBridge runs closures directly under a lock.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any

from winkickoff.mcp import BRIDGE_TIMEOUT
from winkickoff.mcp.errors import ToolError
from winkickoff.mcp.workspace import Workspace

QUEUED, RUNNING, ABANDONED, DONE = "queued", "running", "abandoned", "done"


@dataclass
class Item:
    fn: Callable[[Workspace], Any]
    writes: bool
    deadline: float  # monotonic
    future: Future = field(default_factory=Future)
    state: str = QUEUED
    lock: threading.Lock = field(default_factory=threading.Lock)
    on_late: Callable[[str], None] | None = None  # told when a closure finishes after the caller gave up


class Bridge:
    """A queue of closures for the owning thread. run() from server threads, pump() from the owner."""

    def __init__(self) -> None:
        self._queue: queue.Queue[Item] = queue.Queue()
        self._workspace: Workspace | None = None
        self._lock = threading.Lock()
        self._late: dict[int, Item] = {}
        self._late_seq = 0
        self._closed = False

    @property
    def attached(self) -> bool:
        return self._workspace is not None

    def close(self) -> None:
        """No more closures are accepted (the server stopped); queued ones fail."""
        self._closed = True
        self.fail_all(RuntimeError("server stopped"))

    def reopen(self) -> None:
        self._closed = False

    def attach(self, workspace: Workspace) -> None:
        with self._lock:
            self._workspace = workspace

    def detach(self) -> None:
        with self._lock:
            self._workspace = None

    def run(self, fn: Callable[[Workspace], Any], *, writes: bool, timeout: float) -> Any:
        """Run fn on the owning thread and return its result; ToolError window_timeout when the window did not get
        to it in time (a closure that already started completes and is reported through on_late)."""
        if self._closed:
            raise ToolError("window_timeout", "the server is stopped")
        item = Item(fn, writes, time.monotonic() + timeout)  # queued even while detached: the next window serves it
        self._queue.put(item)
        try:
            return item.future.result(timeout)
        except TimeoutError:
            if item.future.done():  # the closure itself raised a TimeoutError (a stalled drive): not a bridge timeout
                raise
        with item.lock:
            if item.state == QUEUED:
                item.state = ABANDONED
                raise ToolError("window_timeout", f"the editor window did not answer in {timeout:g} s "
                                                  "(busy, a dialog is open, or it is restarting)")
        try:
            return item.future.result(BRIDGE_TIMEOUT)  # it started: give the running closure a little more time
        except TimeoutError:
            if item.future.done():
                raise
            if not writes:  # nothing of a read can land later; nothing to report
                raise ToolError("window_timeout", f"the editor window did not finish in {timeout + BRIDGE_TIMEOUT:g} s") from None
            token = self._remember_late(item)
            raise ToolError("window_timeout", f"the editor window did not finish in {timeout + BRIDGE_TIMEOUT:g} s; "
                                              "the change may still land, check with get_profile",
                            {"pending": token}) from None

    def _remember_late(self, item: Item) -> int:
        with self._lock:
            self._late_seq += 1
            self._late[self._late_seq] = item
            for token in [t for t, late in self._late.items() if late.state == DONE and late.on_late is None][:-16]:
                self._late.pop(token, None)  # finished and never asked about: keep the map small
            return self._late_seq

    def note_late(self, token: int, callback: Callable[[str], None]) -> None:
        """Ask to be told when the late closure of a window_timeout completes (the journal note)."""
        with self._lock:
            item = self._late.pop(token, None)
        if item is None:
            return
        with item.lock:
            if item.state == DONE:
                callback("completed after timeout")
            else:
                item.on_late = callback

    def pump(self, max_items: int = 20, budget: float = 0.05) -> int:
        """Run queued closures on the owning thread; returns how many ran. Called from the window's after() timer."""
        workspace = self._workspace
        if workspace is None:
            return 0
        ran = 0
        started = time.monotonic()
        while ran < max_items and time.monotonic() - started < budget:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            with item.lock:
                if item.state != QUEUED:
                    continue
                if time.monotonic() > item.deadline:
                    item.state = ABANDONED
                    item.future.set_exception(ToolError("window_timeout", "the request expired before the window ran it"))
                    continue
                if item.writes and workspace.is_busy():
                    item.state = DONE
                    item.future.set_exception(ToolError("window_busy", "the window is busy or a dialog is open; try again"))
                    continue
                item.state = RUNNING
            ran += 1
            try:
                result = item.fn(workspace)
            except BaseException as exc:  # noqa: BLE001 - the exception belongs to the caller
                with item.lock:
                    item.state = DONE
                    late = item.on_late
                item.future.set_exception(exc)
            else:
                with item.lock:
                    item.state = DONE
                    late = item.on_late
                item.future.set_result(result)
            if late is not None:
                late("completed after timeout")
        return ran

    def fail_all(self, exc: BaseException) -> None:
        """Fail every queued closure (the server stops or the window closes for good)."""
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            with item.lock:
                if item.state == QUEUED:
                    item.state = ABANDONED
                    item.future.set_exception(exc)


class InlineBridge(Bridge):
    """Runs closures directly on the calling thread (no window): the stdio server and the tests."""

    def __init__(self, workspace: Workspace | None = None) -> None:
        super().__init__()
        self._inline_lock = threading.RLock()
        if workspace is not None:
            self.attach(workspace)

    def run(self, fn: Callable[[Workspace], Any], *, writes: bool, timeout: float) -> Any:
        workspace = self._workspace
        if workspace is None:
            raise ToolError("window_timeout", "no workspace is attached")
        with self._inline_lock:
            return fn(workspace)
