"""pyte screens for the relay analyzer (M0 spike).

AltScreen is the terminal spike's fixed pyte.Screen (alternate screen buffer, private-marker CSI
fix), plus a scroll counter. CaptureScreen also keeps the lines that scroll off the top, so a
command's whole output can be read back as text.
"""

from __future__ import annotations

import pyte

ALT_MODES = {47, 1047, 1049}
BRACKETED_PASTE = 2004 << 5  # pyte stores private modes shifted left by 5


class AltScreen(pyte.Screen):
    PRIVATE_OK = {"set_mode", "reset_mode", "report_device_attributes"}

    def __init__(self, columns: int, lines: int) -> None:
        super().__init__(columns, lines)
        self._saved = None
        self.scrolls = 0       # lines scrolled off the top of the primary screen
        self.alt_used = False  # a full-screen program ran
        # pyte passes private=True to every CSI handler for sequences like ESC[>4;1m, but most
        # handlers don't accept it and the TypeError permanently kills pyte's parser.
        for name in set(pyte.Stream.csi.values()) - self.PRIVATE_OK:
            setattr(self, name, self._drop_private(getattr(self, name)))

    @staticmethod
    def _drop_private(method):
        def wrapper(*args, private=False, **kwargs):
            if not private:
                method(*args, **kwargs)
        return wrapper

    def write_process_input(self, data: str) -> None:
        pass  # the real terminal answers queries, not us

    @property
    def in_alt(self) -> bool:
        return self._saved is not None

    def line_text(self, y: int, x0: int = 0) -> str:
        row = self.buffer[y]
        return "".join(row[x].data for x in range(x0, self.columns)).rstrip()

    def scrolled_off(self, text: str) -> None:
        pass

    def index(self) -> None:
        top, bottom = self.margins or pyte.screens.Margins(0, self.lines - 1)
        if self.cursor.y == bottom and top == 0 and not self.in_alt:
            self.scrolls += 1
            self.scrolled_off(self.line_text(0))
        super().index()

    def set_mode(self, *modes, **kwargs) -> None:
        if kwargs.get("private") and ALT_MODES & set(modes) and self._saved is None:
            self.alt_used = True
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


class CaptureScreen(AltScreen):
    """Screen for one command's output; remembers up to max_lines lines of scrollback."""

    def __init__(self, columns: int, lines: int, max_lines: int = 10000) -> None:
        super().__init__(columns, lines)
        self.max_lines = max_lines
        self.history: list[str] = []
        self.dropped = 0

    def scrolled_off(self, text: str) -> None:
        self.history.append(text)
        if len(self.history) > self.max_lines:
            self.dropped += 1
            del self.history[0]

    def text(self) -> str:
        lines = self.history + [self.line_text(y) for y in range(self.lines)]
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)
