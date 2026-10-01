# SPDX-License-Identifier: GPL-3.0-or-later
"""The backend interface (SPEC §10.2). llama.cpp is the only built-in backend (D5, D35); the interface
stays so another could be added without touching the rest. Calls block: the daemon runs them on a worker
thread, never on the D-Bus main loop.
"""

from __future__ import annotations

import dataclasses
import threading
from typing import Callable


class BackendError(Exception):
    """The model couldn't answer (not loaded, crashed, out of memory, cancelled...). The message is
    plain words for the user."""


class Cancelled(BackendError):
    pass


@dataclasses.dataclass
class Status:
    state: str = "off"           # off | loading | ready | error
    model: str = ""              # the model's name as the user sees it
    build: str = ""              # cuda | vulkan | cpu
    context: int = 0
    reduced: str = ""            # why this isn't the full profile, in plain words ("" = full)
    detail: str = ""             # last error or note


class InferenceBackend:
    def status(self) -> Status:
        raise NotImplementedError

    def load(self) -> None:
        """Load the model (blocking); raises BackendError if no profile works."""
        raise NotImplementedError

    def unload(self) -> None:
        raise NotImplementedError

    def chat(self, messages: list[dict], *, schema: dict | None = None, max_tokens: int = 600,
             on_text: Callable[[str], None] | None = None, cancel: threading.Event | None = None,
             sampling: dict | None = None) -> tuple[str, dict]:
        """One reply; streams text pieces to on_text. Returns (full text, timings). sampling: temperature,
        top_p, … for writing; tool calls leave it out."""
        raise NotImplementedError
