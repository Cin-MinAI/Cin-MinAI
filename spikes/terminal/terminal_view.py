"""Textual widget rendering a pyte screen fed by a PtySession (M0 spike)."""

from __future__ import annotations

from functools import lru_cache

import pyte
from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.message import Message
from textual.strip import Strip
from textual.widget import Widget

from pty_session import PtySession

# pyte stores private (DEC) modes shifted left by 5.
DECCKM = 1 << 5
BRACKETED_PASTE = 2004 << 5
DECTCEM = 25 << 5
ALT_MODES = {47, 1047, 1049}

FPS = 30


class AltScreen(pyte.Screen):
    """pyte.Screen plus the alternate screen buffer (vim/less/htop), which pyte lacks."""

    # CSI handlers in pyte that understand the private ("?", ">") marker.
    PRIVATE_OK = {"set_mode", "reset_mode", "report_device_attributes"}

    def __init__(self, columns: int, lines: int) -> None:
        super().__init__(columns, lines)
        self._saved = None
        self.responder = None
        # pyte passes private=True to every CSI handler for sequences like
        # ESC[>4;1m (xterm modifyOtherKeys), but most handlers don't accept it
        # and the TypeError permanently kills pyte's parser generator.
        for name in set(pyte.Stream.csi.values()) - self.PRIVATE_OK:
            setattr(self, name, self._drop_private(getattr(self, name)))

    @staticmethod
    def _drop_private(method):
        def wrapper(*args, private=False, **kwargs):
            if not private:
                method(*args, **kwargs)
        return wrapper

    def write_process_input(self, data: str) -> None:
        # Replies to terminal queries (device attributes, cursor position).
        if self.responder:
            self.responder(data.encode())

    def set_mode(self, *modes, **kwargs) -> None:
        if kwargs.get("private") and ALT_MODES & set(modes) and self._saved is None:
            self._saved = (
                {y: dict(line) for y, line in self.buffer.items()},
                self.cursor.x,
                self.cursor.y,
            )
            self.buffer.clear()
            self.dirty.update(range(self.lines))
        super().set_mode(*modes, **kwargs)

    def reset_mode(self, *modes, **kwargs) -> None:
        if kwargs.get("private") and ALT_MODES & set(modes) and self._saved is not None:
            lines, x, y = self._saved
            self._saved = None
            self.buffer.clear()
            for row, chars in lines.items():
                if row < self.lines:
                    self.buffer[row].update(chars)
            self.cursor_position(y + 1, x + 1)
            self.dirty.update(range(self.lines))
        super().reset_mode(*modes, **kwargs)


NAMED = {
    "black": "black", "red": "red", "green": "green", "brown": "yellow",
    "blue": "blue", "magenta": "magenta", "cyan": "cyan", "white": "white",
}
NAMED.update({f"bright{k}": f"bright_{v}" for k, v in NAMED.items()})
NAMED["brightbrown"] = "bright_yellow"


def _color(value: str) -> str | None:
    if value == "default":
        return None
    if value in NAMED:
        return NAMED[value]
    if len(value) == 6:
        return f"#{value}"
    return None


@lru_cache(maxsize=4096)
def _style(fg, bg, bold, italics, underscore, strike, reverse, cursor) -> Style:
    return Style(
        color=_color(fg), bgcolor=_color(bg), bold=bold, italic=italics,
        underline=underscore, strike=strike, reverse=reverse != cursor,
    )


KEYS = {
    "enter": "\r", "tab": "\t", "shift+tab": "\x1b[Z", "escape": "\x1b",
    "backspace": "\x7f", "ctrl+h": "\x7f", "delete": "\x1b[3~", "insert": "\x1b[2~",
    "home": "\x1b[H", "end": "\x1b[F", "pageup": "\x1b[5~", "pagedown": "\x1b[6~",
    "f1": "\x1bOP", "f2": "\x1bOQ", "f3": "\x1bOR", "f4": "\x1bOS",
    "f5": "\x1b[15~", "f6": "\x1b[17~", "f7": "\x1b[18~", "f8": "\x1b[19~",
    "f9": "\x1b[20~", "f10": "\x1b[21~", "f11": "\x1b[23~", "f12": "\x1b[24~",
    "ctrl+space": "\x00", "ctrl+backslash": "\x1c", "ctrl+right_square_bracket": "\x1d",
}
ARROWS = {"up": "A", "down": "B", "right": "C", "left": "D"}


class TerminalView(Widget, can_focus=True):
    DEFAULT_CSS = "TerminalView { width: 1fr; height: 1fr; }"

    class Exited(Message):
        def __init__(self, status: int) -> None:
            super().__init__()
            self.status = status

    def __init__(self, argv: list[str] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session = PtySession(argv)
        self.term: AltScreen | None = None
        self.stream: pyte.ByteStream | None = None
        self._pending = False
        self.bytes_in = 0
        self.parse_errors = 0

    # ---- lifecycle -------------------------------------------------------

    def on_resize(self, event: events.Resize) -> None:
        # event.size includes the border; the PTY must match the content area.
        cols, rows = max(self.size.width, 2), max(self.size.height, 2)
        if self.term is None:
            self.term = AltScreen(cols, rows)
            self.term.responder = self.session.write
            self.stream = pyte.ByteStream(self.term)
            self.session.start(cols, rows, self._output, self._exited)
            self.set_interval(1 / FPS, self._tick)
        else:
            self.term.resize(rows, cols)
            self.session.resize(cols, rows)
        self.refresh()

    def on_unmount(self) -> None:
        self.session.close()

    def _output(self, data: bytes) -> None:
        self.bytes_in += len(data)
        try:
            self.stream.feed(data)
        except Exception as e:
            # A parser exception leaves pyte's generator dead; never let one
            # sequence take the whole terminal down.
            self.parse_errors += 1
            self.log.error(f"pyte parse error: {e!r}")
            self.stream = pyte.ByteStream(self.term)
        self._pending = True

    def _exited(self, status: int) -> None:
        self.post_message(self.Exited(status))

    def _tick(self) -> None:
        if self._pending:
            self._pending = False
            self.term.dirty.clear()
            self.refresh()

    # ---- rendering -------------------------------------------------------

    def render_line(self, y: int) -> Strip:
        term = self.term
        if term is None or y >= term.lines:
            return Strip.blank(self.size.width)
        line = term.buffer[y]
        show_cursor = self.has_focus and term.cursor.y == y and DECTCEM in term.mode
        segments: list[Segment] = []
        run: list[str] = []
        run_key = None
        for x in range(term.columns):
            ch = line[x]
            if not ch.data:  # right half of a wide char
                continue
            key = (ch.fg, ch.bg, ch.bold, ch.italics, ch.underscore,
                   ch.strikethrough, ch.reverse, show_cursor and x == term.cursor.x)
            if key != run_key and run:
                segments.append(Segment("".join(run), _style(*run_key)))
                run = []
            run_key = key
            run.append(ch.data)
        if run:
            segments.append(Segment("".join(run), _style(*run_key)))
        return Strip(segments)

    def display_text(self) -> str:
        return "\n".join(self.term.display) if self.term else ""

    # ---- input -----------------------------------------------------------

    def _encode(self, event: events.Key) -> str | None:
        key = event.key
        if key in ARROWS:
            prefix = "\x1bO" if DECCKM in self.term.mode else "\x1b["
            return prefix + ARROWS[key]
        if key.startswith("ctrl+") and key[5:] in ARROWS:
            return f"\x1b[1;5{ARROWS[key[5:]]}"
        if key in KEYS:
            return KEYS[key]
        if key.startswith("ctrl+") and len(key) == 6 and key[5].isalpha():
            return chr(ord(key[5]) - 96)
        if key.startswith("alt+") and event.character:
            return "\x1b" + event.character
        if event.character and event.is_printable:
            return event.character
        return None

    def on_key(self, event: events.Key) -> None:
        if self.term is None:
            return
        data = self._encode(event)
        if data is not None:
            event.stop()
            event.prevent_default()
            self.session.write(data.encode())

    def on_paste(self, event: events.Paste) -> None:
        text = event.text
        if BRACKETED_PASTE in self.term.mode:
            text = f"\x1b[200~{text}\x1b[201~"
        self.session.write(text.encode())
        event.stop()
