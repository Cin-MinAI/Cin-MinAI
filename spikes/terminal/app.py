"""Split-pane spike app: real shell on the left, fake token stream on the right.

Run interactively:  python app.py
Quit: Ctrl-Q
"""

from __future__ import annotations

import random
import time

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Log, Static

from terminal_view import TerminalView

WORDS = ("the build failed because the linker could not resolve usb_init "
         "check the CMakeLists target_link_libraries entry and rerun make ").split()


class SpikeApp(App):
    CSS = """
    Horizontal { height: 1fr; }
    #term { border: round $accent; }
    #assistant { width: 1fr; border: round $secondary; }
    #status { height: 1; background: $panel; }
    """
    BINDINGS = [Binding("ctrl+q", "quit", "Quit", priority=True)]

    def __init__(self, tokens_per_sec: float = 40.0) -> None:
        super().__init__()
        self.tokens_per_sec = tokens_per_sec
        self.tick_times: list[float] = []

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield TerminalView(id="term")
            yield Log(id="assistant", highlight=False)
        yield Static("", id="status")

    def on_mount(self) -> None:
        self.query_one(TerminalView).focus()
        self.set_interval(1 / self.tokens_per_sec, self._stream_token)
        self.set_interval(0.5, self._status)

    def _stream_token(self) -> None:
        self.tick_times.append(time.perf_counter())
        self.query_one(Log).write(random.choice(WORDS) + " ")

    def _status(self) -> None:
        term = self.query_one(TerminalView)
        size = f"{term.term.columns}x{term.term.lines}" if term.term else "-"
        self.query_one("#status", Static).update(
            f" pty: {size}  bytes in: {term.bytes_in:,}  stream ticks: {len(self.tick_times)}"
        )

    def max_tick_gap(self, since: float = 0.0) -> float:
        ts = [t for t in self.tick_times if t >= since]
        return max((b - a for a, b in zip(ts, ts[1:])), default=0.0)

    def on_terminal_view_exited(self, message: TerminalView.Exited) -> None:
        self.query_one(Log).write_line(f"\n[shell exited with status {message.status}]")


if __name__ == "__main__":
    SpikeApp().run()
