"""Headless acceptance checks for the terminal spike (maps to spec §51).

Drives the real app through Textual's Pilot with real keypresses into a real
bash PTY, then inspects the emulated screen. Prints a PASS/FAIL table.

    python check.py            # all checks
    python check.py -k vim     # checks whose name contains "vim"
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import time
from pathlib import Path

import pyte

from app import SpikeApp
from terminal_view import TerminalView

OUT = Path(__file__).parent / "out"
results: list[tuple[str, bool, str]] = []


def hide(marker: str) -> str:
    """Spell a marker so the typed command line never matches it, only the output."""
    return f'{marker[:2]}""{marker[2:]}'


class Harness:
    def __init__(self, app: SpikeApp, pilot) -> None:
        self.app, self.pilot = app, pilot
        self.term: TerminalView = app.query_one(TerminalView)

    def text(self) -> str:
        return self.term.display_text()

    async def type(self, s: str) -> None:
        # Straight to the PTY: Pilot.press waits for app idle (~0.9s/key here,
        # since the render timer never lets it idle). Special keys still go
        # through Pilot + TerminalView._encode via key().
        self.term.session.write(s.encode())
        await self.pilot.pause(0.05)

    async def key(self, *keys: str) -> None:
        await self.pilot.press(*keys)

    async def wait(self, pred, timeout: float = 5.0) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if pred():
                return True
            await self.pilot.pause(0.05)
        return pred()

    async def wait_text(self, needle: str, timeout: float = 5.0) -> bool:
        return await self.wait(lambda: needle in self.text(), timeout)

    async def run(self, cmd: str, timeout: float = 5.0) -> bool:
        """Type cmd + marker echo, press Enter, wait for the marker in output."""
        marker = f"MK{int(time.monotonic() * 1000) % 10**8}"
        await self.type(f"{cmd}; echo {hide(marker)}")
        await self.key("enter")
        return await self.wait_text(marker, timeout)

    async def clear(self) -> None:
        await self.run("clear")


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


# ---- checks ---------------------------------------------------------------

async def check_state_persists(h: Harness) -> None:
    await h.run("cd /tmp")
    await h.run("export SPIKE_VAR=hello42")
    await h.type('echo "$PWD:$SPIKE_VAR"')
    await h.key("enter")
    record("cd + export persist", await h.wait_text("/tmp:hello42"))


async def check_printable_keys(h: Harness) -> None:
    await h.clear()
    await h.key(*"echo ab", "enter")
    record("printable keys via Textual key events", await h.wait(
        lambda: any(l.strip() == "ab" for l in h.term.term.display), 3))


async def check_ctrl_c(h: Harness) -> None:
    await h.type("sleep 30")
    await h.key("enter")
    await h.pilot.pause(0.5)
    t0 = time.monotonic()
    await h.key("ctrl+c")
    ok = await h.run("true", timeout=3)
    record("Ctrl-C interrupts foreground job", ok, f"{time.monotonic() - t0:.2f}s")


async def check_ctrl_z(h: Harness) -> None:
    await h.type("sleep 31")
    await h.key("enter")
    await h.pilot.pause(0.5)
    await h.key("ctrl+z")
    ok = await h.wait_text("Stopped", 3)
    await h.run("kill %1")
    record("Ctrl-Z suspends job", ok)


async def check_sgr_colors(h: Harness) -> None:
    await h.clear()
    await h.run(r"printf '\033[1;31mREDTEXT\033[0m\n'")
    term = h.term.term
    found = [
        ch for row in term.buffer.values() for ch in row.values()
        if ch.data == "R" and ch.fg == "red" and ch.bold
    ]
    record("SGR bold red rendered", bool(found))
    h.app.save_screenshot(str(OUT / "colors.svg"))


async def check_vim(h: Harness) -> None:
    editor = "vim" if shutil.which("vim") else "vi"
    target = "/tmp/cinmin_spike.txt"
    Path(target).unlink(missing_ok=True)
    await h.clear()
    await h.type(f"{editor} -u NONE -N {target}")
    await h.key("enter")
    ok_open = await h.wait(lambda: h.text().count("~") >= 3, 5)
    await h.key("i")
    await h.type("hello vim")
    await h.key("escape")
    h.app.save_screenshot(str(OUT / "vim.svg"))
    await h.type(":wq")
    await h.key("enter")
    ok_back = await h.wait_text("cinmin_spike", 3)  # primary screen restored
    await h.run(f"cat {target}")
    ok_file = "hello vim" in h.text()
    record(f"{editor}: open/edit/save", ok_open and ok_file, f"open={ok_open} file={ok_file}")
    record("alt screen restored after editor", ok_back)


async def check_less(h: Harness) -> None:
    await h.clear()
    await h.type("seq 1 500 | less")
    await h.key("enter")
    ok_open = await h.wait(lambda: h.term.term.display[0].strip() == "1", 5)
    await h.key("space")
    ok_page = await h.wait(lambda: h.term.term.display[0].strip() != "1", 3)
    await h.key("q")
    ok_quit = await h.run("true", 3)
    record("less: page + quit", ok_open and ok_page and ok_quit,
           f"open={ok_open} page={ok_page} quit={ok_quit}")


async def check_top(h: Harness) -> None:
    await h.clear()
    await h.type("top -d 0.5")
    await h.key("enter")
    ok_open = await h.wait_text("load average", 5)
    h.app.save_screenshot(str(OUT / "top.svg"))
    await h.key("q")
    ok_quit = await h.run("true", 3)
    record("top: render + quit", ok_open and ok_quit, f"open={ok_open} quit={ok_quit}")


async def check_python_repl(h: Harness) -> None:
    await h.clear()
    await h.type("python3 -q")
    await h.key("enter")
    ok_prompt = await h.wait_text(">>>", 5)
    await h.type("6*7")
    await h.key("enter")
    ok_eval = await h.wait(lambda: any(l.strip() == "42" for l in h.term.term.display), 3)
    await h.key("ctrl+d")
    ok_exit = await h.run("true", 3)
    record("python REPL", ok_prompt and ok_eval and ok_exit,
           f"prompt={ok_prompt} eval={ok_eval} exit={ok_exit}")


async def check_resize(h: Harness) -> None:
    if not hasattr(h.pilot, "resize_terminal"):
        record("resize propagates to PTY", False, "Pilot.resize_terminal unavailable")
        return
    await h.pilot.resize_terminal(130, 36)
    await h.pilot.pause(0.3)
    await h.clear()
    term = h.term.term
    expect = f"{term.lines} {term.columns}"
    await h.run("stty size")
    ok = expect in h.text()
    widget = h.term.size
    record("resize propagates to PTY", ok and (widget.width, widget.height) == (term.columns, term.lines),
           f"pyte={term.columns}x{term.lines} widget={widget.width}x{widget.height}")
    await h.pilot.resize_terminal(160, 48)
    await h.pilot.pause(0.3)


async def check_throughput(h: Harness) -> None:
    for label, cmd in (("100k short lines", "yes | head -100000"),
                       ("200k seq lines", "seq 1 200000"),
                       ("colored ls -R /usr/share (20k)", "ls -R --color=always /usr/share | head -20000")):
        await h.clear()
        before = h.term.bytes_in
        t0 = time.perf_counter()
        ok = await h.run(cmd, timeout=120)
        dt = time.perf_counter() - t0
        mb = (h.term.bytes_in - before) / 1e6
        gap = h.app.max_tick_gap(since=t0)
        record(f"throughput: {label}", ok,
               f"{dt:.2f}s  {mb:.1f} MB  {mb / dt:.2f} MB/s  max UI stall {gap * 1000:.0f} ms")


async def check_ui_responsive_idle(h: Harness) -> None:
    t0 = time.perf_counter()
    await h.pilot.pause(2.0)
    gap = h.app.max_tick_gap(since=t0)
    record("assistant stream smooth while idle", gap < 0.1, f"max gap {gap * 1000:.0f} ms")


async def check_shell_exit(h: Harness) -> None:
    await h.type("exit")
    await h.key("enter")
    ok = await h.wait(lambda: not h.term.session.alive, 3)
    t0 = time.perf_counter()
    await h.pilot.pause(1.0)
    still_streaming = h.app.max_tick_gap(since=t0) < 0.2 and h.app.is_running
    record("shell exit leaves app running", ok and still_streaming,
           f"exit_status={h.term.session.exit_status}")


CHECKS = [
    check_state_persists, check_printable_keys, check_ctrl_c, check_ctrl_z, check_sgr_colors,
    check_vim, check_less, check_top, check_python_repl, check_resize,
    check_ui_responsive_idle, check_throughput, check_shell_exit,
]


def pyte_microbench() -> None:
    lines = b"".join(b"%d\n" % i for i in range(200_000))
    screen = pyte.Screen(80, 24)
    stream = pyte.ByteStream(screen)
    t0 = time.perf_counter()
    stream.feed(lines)
    dt = time.perf_counter() - t0
    record("pyte raw feed (no UI)", True, f"{len(lines) / 1e6:.1f} MB in {dt:.2f}s = {len(lines) / 1e6 / dt:.2f} MB/s")


async def main(filter_: str | None) -> int:
    OUT.mkdir(exist_ok=True)
    pyte_microbench()
    app = SpikeApp()
    async with app.run_test(size=(160, 48)) as pilot:
        h = Harness(app, pilot)
        if not await h.wait(lambda: h.term.session.alive and h.text().strip(), 10):
            record("shell started", False)
            return 1
        await h.run("true", 10)
        for check in CHECKS:
            if filter_ and filter_ not in check.__name__:
                continue
            try:
                await check(h)
            except Exception as e:  # keep going; a spike wants the full picture
                record(check.__name__, False, f"{type(e).__name__}: {e}")
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", dest="filter")
    sys.exit(asyncio.run(main(ap.parse_args().filter)))
