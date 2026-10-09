# SPDX-License-Identifier: GPL-3.0-or-later
"""Seeing, the same way for any target (PLAN §1b, the look closure): facts by code first, the checks, the permissions
by target, one question to the picture model, and the record.

    python3 -m unittest tests.unit.test_aicui_look -v        (from the repo root)
"""

import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(__file__))

from test_aicui_agent import Scripted  # noqa: E402

from cin_minai.aicui import look  # noqa: E402
from cin_minai.aicui.agent import Agent  # noqa: E402

try:
    import PIL  # noqa: F401  (a dependency of cinminai-aicui; the dev box's WSL may not have it)
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

TREE = '''
xwininfo: Window id: 0x3d5 (the root window) (has no name)

  Root window id: 0x3d5 (the root window) (has no name)
  Parent window id: 0x0 (none)
     2 children:
     0x200001 "pygame window": ("pygame" "pygame")  1280x720+0+0  +0+0
        1 child:
        0x200002 (has no name): ()  1280x720+0+0  +0+0
     0x200005 (has no name): ()  10x10+0+0  +0+0
'''
SCREEN = (4095, 2160, 3)


def png(path: str, colours: int = 3) -> None:
    from PIL import Image
    im = Image.new("RGB", (4095, 2160), (10, 10, 10))
    for i in range(colours - 1):
        im.paste((200, 30 * i, 30), (100 + 200 * i, 100, 280 + 200 * i, 300))
    im.save(path)


class Facts(unittest.TestCase):
    def test_the_windows_from_the_tree(self):
        self.assertEqual(look.windows(TREE, SCREEN),
                         [{"name": "pygame window", "width": 1280, "height": 720, "x": 0, "y": 0}])

    def test_what_code_finds_before_any_model_looks(self):
        facts = {"screen": {"width": 4095, "height": 2160, "scale": 3}, "program": "run.sh", "running": True,
                 "windows": [{"name": "game", "width": 1280, "height": 720, "x": 0, "y": 0},
                             {"name": "tools", "width": 900, "height": 700, "x": 3600, "y": 0}],
                 "picture": {"colours": 1}}
        found = look.checks(facts)
        self.assertIn("game is 1280x720: 31% of the screen's width (at 3x scaling other windows are drawn 3x larger)",
                      found)
        self.assertIn("tools (900x700 at 3600,0) runs off the 4095x2160 screen", found)
        self.assertIn("the picture is blank (one colour): nothing was drawn", found)
        stopped = look.checks({**facts, "running": False, "windows": [], "output": "No module named pygame"})
        self.assertIn("the program had stopped before the picture was taken: No module named pygame", stopped)

    def test_the_program_runs_at_the_persons_screen_inside_the_sandbox(self):
        script = look.program_script("run.sh", "/p/.venv", SCREEN, ".cinminai/looks/x")
        self.assertIn("mkdir -p -m 1777 /tmp/.X11-unix; Xvfb :77 -screen 0 4095x2160x24 -nolisten tcp -extension GLX",
                      script)
        self.assertIn("GDK_SCALE=3", script)
        self.assertIn("-video_size 4095x2160 -i :77", script)
        self.assertIn("( bash run.sh )", script)
        self.assertEqual(look.screen_of({"CINMINAI_SCREEN": "4095x2160@3"}), SCREEN)
        self.assertEqual(look.screen_of({}), (1920, 1080, 1))


@unittest.skipUnless(shutil.which("git") and HAVE_PIL, "needs git and Pillow")
class Looking(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        with open(os.path.join(self.root, "run.sh"), "w") as f:
            f.write("python3 main.py\n")
        self.asked = []
        p = mock.patch.dict(os.environ, {"CINMINAI_SCREEN": "4095x2160@3", "DISPLAY": ":0"})
        p.start()
        self.addCleanup(p.stop)

    def agent(self, replies=()):
        replies = list(replies)
        a = Agent(self.root, Scripted([]), "m", "auto", say=lambda s: None,
                  ask=lambda q: (self.asked.append(q), replies.pop(0) if replies else "n")[1])
        return a

    def test_a_look_at_the_program(self):
        a = self.agent()
        questions = []

        def execute(command, timeout, sandbox):  # what the script does in the sandbox: a picture, the windows, the output
            base = command.split("> ")[1].split(".out")[0].strip("'")
            png(os.path.join(self.root, base + ".png"))
            with open(os.path.join(self.root, base + ".windows"), "w") as f:
                f.write(TREE)
            open(os.path.join(self.root, base + ".out"), "w").close()
            return 0, "running=yes"
        a.execute = execute
        a.reader = lambda: (lambda messages, **kw: (questions.append(messages), ("No: the buttons are cut off.", {}))[1])
        with mock.patch("shutil.which", return_value="/usr/bin/Xvfb"):
            out = a.do({"tool": "look", "target": "program", "question": "Are the buttons visible?", "address": ""})
        self.assertTrue(out.startswith("Looked at program"))
        self.assertIn('window "pygame window": 1280x720 at 0,0', out)
        self.assertIn("pygame window is 1280x720: 31% of the screen's width", out)
        self.assertIn('asked "Are the buttons visible?": No: the buttons are cut off.', out)
        self.assertEqual(self.asked, [])  # its own output: no question
        sent = questions[0][0]["content"]
        self.assertEqual(sent[0]["type"], "image_url")  # the window itself, cropped
        self.assertIn("Code already found: pygame window is 1280x720", sent[1]["text"])
        saved = [f for f in os.listdir(os.path.join(self.root, ".cinminai", "looks")) if f.endswith(".json")]
        with open(os.path.join(self.root, ".cinminai", "looks", saved[0])) as f:
            facts = json.load(f)
        self.assertEqual((facts["running"], facts["answer"]), (True, "No: the buttons are cut off."))

    def test_the_persons_screen_is_asked_twice_and_shown_first(self):
        a = self.agent(["y", "n"])

        def run(argv, **kw):
            if argv[0] == "ffmpeg":
                png(argv[-1])
            return types.SimpleNamespace(stdout="0x1 0 0 0 800 600 host Firefox — a page\n", returncode=0)
        with mock.patch("subprocess.run", side_effect=run):
            out = a.do({"tool": "look", "target": "screen", "question": "What is open?", "address": ""})
        self.assertEqual(out, "the person said no to the AI looking at their screen")
        self.assertIn("you'll see it before the AI does", self.asked[0])
        self.assertIn("it's in AICUI's chat", self.asked[1])
        self.assertEqual([f for f in os.listdir(os.path.join(self.root, ".cinminai", "looks")) if f.endswith(".png")],
                         [])  # declined: the picture is gone
        self.assertEqual(self.agent(["n"]).do({"tool": "look", "target": "screen", "question": "q", "address": ""}),
                         "the person said no to a picture of their screen")

    def test_a_page_is_asked_and_must_be_https(self):
        a = self.agent(["n"])
        self.assertIn("https://", a.do({"tool": "look", "target": "page", "question": "q", "address": "gui.py"}))
        self.assertEqual(a.do({"tool": "look", "target": "page", "question": "q", "address": "https://x.org/"}),
                         "the person said no to looking at https://x.org/")


if __name__ == "__main__":
    unittest.main()
