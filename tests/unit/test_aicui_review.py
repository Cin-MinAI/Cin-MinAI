# SPDX-License-Identifier: GPL-3.0-or-later
"""AICUI's Review (PLAN D94, aicui/review.py): three passes by another model, merged, and every claim checked in
code where it can be — the quoted line, the compiler, the file's names, the program started — before the person sees
it. The model is the Models view's Review job."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))

from test_jobs import BIG, machine  # noqa: E402

from cin_minai.aicui import review  # noqa: E402
from cin_minai.daemon import jobs  # noqa: E402
from cin_minai.daemon.models import ModelStore  # noqa: E402
from cin_minai.inference import matcher  # noqa: E402
from cin_minai.sidebar import words  # noqa: E402

MAIN = """import json
import tkinter as tk


def load():
    with open('data/cards.json') as f:
        return json.load(f)


class App:
    def __init__(self, root):
        self.root = root
        self.button = tk.Button(root, text="Start", command=self.start)

    def start(self):
        if hasattr(self.root, 'show_view'):
            self.root.show_view("board")
"""

# what the 35B wrote on the NVMe (2026-10-24), shortened: one true defect, a made-up syntax error, a name "not
# imported" that is, an unconditional crash at startup, a conditional one, and the true one again from another pass
ANSWER = """Here are the defects.

### main.py:16
quote: if hasattr(self.root, 'show_view'):
wrong: `self.root` is the Tk window, which has no `show_view`, so Start never opens the board.
sees: Clicking Start does nothing.

### main.py:7
quote: return json.load(f)
wrong: SyntaxError: missing closing parenthesis on this line.
sees: The program crashes immediately.

### main.py:7
quote: return json.load(f)
wrong: `json` is not imported in this scope, NameError.
sees: Crash when loading.

### `main.py`:1
quote: import json
wrong: The application crashes on launch before any window appears.
sees: Nothing opens.

### main.py:6
quote: with open('data/cards.json') as f:
wrong: If data/cards.json is missing, the program crashes at startup with FileNotFoundError.
sees: A traceback.

### other.py:3
quote: x = 1
wrong: Something about a file that isn't there.
sees: Nothing.

Verdict: not done
"""

AGAIN = """### main.py:17
quote: if hasattr(self.root, 'show_view'):
wrong: Start checks `show_view` on the window, not the app: it never switches to the board.
sees: Start does nothing and the board never opens.

Verdict: done
"""


class Project(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        with open(os.path.join(self.root, "main.py"), "w") as f:
            f.write(MAIN)
        os.makedirs(os.path.join(self.root, ".cinminai"))
        with open(os.path.join(self.root, "original-request.txt"), "w") as f:
            f.write("A card game with a board to play on.")


class Parse(Project):
    def test_blocks_and_verdict(self):
        got = review.parse(ANSWER, "beginning")
        self.assertEqual([(f["file"], f["line"]) for f in got],
                         [("main.py", 16), ("main.py", 7), ("main.py", 7), ("main.py", 1), ("main.py", 6),
                          ("other.py", 3)])
        self.assertEqual(got[0]["quote"], "if hasattr(self.root, 'show_view'):")
        self.assertIn("never opens the board", got[0]["wrong"])
        self.assertEqual(got[0]["sees"], "Clicking Start does nothing.")
        self.assertEqual(review.verdict(ANSWER), "not done")
        self.assertEqual(review.verdict(AGAIN), "done")

    def test_fragments_and_floods_are_left_out(self):
        """2026-10-24: given too much room, a pass listed lines ("Stores root.") and ended in "Y=780.", "No"."""
        many = "".join(f"### main.py:{i}\nquote: x\nwrong: A real sentence about what is wrong on line {i}.\nsees: x\n\n"
                       for i in range(1, 41))
        short = "### main.py:3\nquote: x\nwrong: No\nsees: x\n"
        got = review.kept(review.parse(short + many, "beginning"))
        self.assertEqual(len(got), review.PER_PASS)
        self.assertEqual(got[0]["line"], 1)  # the fragment is gone, the order kept

    def test_the_same_defect_from_two_passes_is_one(self):
        merged = review.merge([review.parse(ANSWER, "beginning"), review.parse(AGAIN, "operation")])
        start = [f for f in merged if f["line"] in (16, 17)]
        self.assertEqual(len(start), 1)
        self.assertEqual(start[0]["passes"], ["beginning", "operation"])
        self.assertEqual(len(merged), 6)  # the two line-7 claims are different claims


class Checks(Project):
    def checked(self, started=None):
        shown = ["main.py"]
        return [(f["line"], *review.check(self.root, shown, f, started)) for f in review.parse(ANSWER, "beginning")]

    def test_made_up_claims_are_dropped(self):
        got = self.checked({"entry": "main.py", "started": True, "code": 124, "out": ""})
        states = {line: (state, why) for line, state, why in got if line != 7}
        self.assertEqual(states[16], ("not checked", ""))  # true, but no check can show it: the person judges
        self.assertEqual(states[1][0], "wrong")  # "crashes on launch": it ran for 5 s
        self.assertIn("ran for 5 seconds", states[1][1])
        self.assertEqual(states[6], ("not checked", ""))  # "if data/cards.json is missing": a condition
        self.assertEqual(states[3][0], "wrong")
        self.assertIn("no file other.py", states[3][1])
        seven = [(state, why) for line, state, why in got if line == 7]
        self.assertEqual(seven[0][0], "wrong")
        self.assertIn("compiles", seven[0][1])
        self.assertEqual(seven[1][0], "wrong")
        self.assertIn("`json` is imported", seven[1][1])

    def test_a_crash_that_happens_is_checked(self):
        got = self.checked({"entry": "main.py", "started": False, "code": 1, "out": "Traceback…"})
        self.assertEqual([s for line, s, _ in got if line == 1], ["checked"])

    def test_a_real_syntax_error_is_checked(self):
        with open(os.path.join(self.root, "main.py"), "a") as f:
            f.write("def broken(:\n")
        got = self.checked()
        self.assertEqual(next(s for line, s, _ in got if line == 7), "checked")

    def test_a_quote_on_another_line_moves_the_finding(self):
        f = {"file": "main.py", "line": 40, "quote": "self.root.show_view(\"board\")", "wrong": "x", "sees": ""}
        self.assertEqual(review.place(self.root, ["main.py"], f), "")
        self.assertEqual(f["line"], 17)
        f = {"file": "main.py", "line": 3, "quote": "print('never written')", "wrong": "x", "sees": ""}
        self.assertIn("isn't in main.py", review.place(self.root, ["main.py"], f))

    def test_a_true_finding_that_says_defined_stays(self):
        """2026-10-24: "`start` is defined as …" was dropped by the name check (it read "is defined" as a claim)."""
        f = {"file": "main.py", "line": 15, "quote": "def start(self):", "sees": "",
             "wrong": "`start` is defined as a method that never opens the board."}
        self.assertEqual(review.check(self.root, ["main.py"], f, None), ("not checked", ""))

    def test_a_button_that_never_starts_the_game_isnt_a_startup_crash(self):
        """2026-10-24: "the game never starts" (the Start button) was dropped because the program itself started."""
        f = {"file": "main.py", "line": 16, "quote": "if hasattr(self.root, 'show_view'):", "sees": "",
             "wrong": "Clicking Start Game crashes with AttributeError, so the game never starts."}
        started = {"entry": "main.py", "started": True, "code": 124, "out": ""}
        self.assertEqual(review.check(self.root, ["main.py"], f, started)[0], "not checked")

    def test_a_quote_of_two_lines(self):
        """The 35B quoted two lines under `quote:`; joined into one, the place check couldn't find it."""
        got = review.parse("### main.py:6-7\nquote:\nwith open('data/cards.json') as f:\n    return json.load(f)\n"
                           "wrong: it reads a relative path.\nsees: nothing\n", "end")
        self.assertEqual(got[0]["quote"], "with open('data/cards.json') as f:\nreturn json.load(f)")
        self.assertEqual(review.place(self.root, ["main.py"], got[0]), "")
        self.assertEqual(got[0]["line"], 6)

    def test_an_attribute_never_set_isnt_dropped(self):
        """2026-10-25 (all three passes): "`self.detail_name` is never defined … the widget is `self.card_name_label`"
        was checked against `self`, found, and dropped; clicking a card did crash."""
        with open(os.path.join(self.root, "main.py"), "a") as f:
            f.write("\n    def show(self, card):\n        self.card_name_label = None\n"
                    "        self.detail_name.setText(card)\n")
        f = {"file": "main.py", "line": 44, "quote": "self.detail_name.setText(card)", "sees": "AttributeError",
             "wrong": "`self.detail_name` is never defined in the class. The actual widget created for this purpose "
                      "is `self.card_name_label` (line 43)."}
        self.assertEqual(review.check(self.root, ["main.py"], f, None),
                         ("not checked", "nothing in main.py sets `detail_name`"))
        f["wrong"] = "`self.card_name_label` is never defined, so showing a card crashes."
        state, why = review.check(self.root, ["main.py"], f, None)  # set only in a method that may never run: kept
        self.assertEqual((state, why[:38]), ("not checked", "main.py sets `card_name_label` on line"))

    def test_a_module_in_the_project_isnt_missing(self):
        """2026-10-25: "`DeckBuilderScreen` is imported from `gui.deck_builder`, but this module is not provided"
        (the file was left out for room): `import DeckBuilderScreen` failed and made it the first checked finding."""
        os.makedirs(os.path.join(self.root, "gui"))
        open(os.path.join(self.root, "gui", "deck_builder.py"), "w").close()
        with open(os.path.join(self.root, "main.py"), "a") as f:
            f.write("from gui.deck_builder import DeckBuilderScreen\n")
        f = {"file": "main.py", "line": 42, "quote": "from gui.deck_builder import DeckBuilderScreen", "sees": "x",
             "wrong": "`DeckBuilderScreen` is imported from `gui.deck_builder`, but this module is not provided: "
                      "ModuleNotFoundError on startup."}
        with mock.patch.object(review, "importable", side_effect=AssertionError("a class isn't a library")):
            self.assertEqual(review.check(self.root, ["main.py"], f, None),
                             ("wrong", "gui/deck_builder.py is in the project"))

    def test_a_file_named_without_its_folder(self):
        os.makedirs(os.path.join(self.root, "gui"))
        shutil.move(os.path.join(self.root, "main.py"), os.path.join(self.root, "gui", "main.py"))
        f = {"file": "main.py", "line": 16, "quote": "", "wrong": "x", "sees": ""}
        self.assertEqual(review.place(self.root, ["gui/main.py"], f), "")
        self.assertEqual(f["file"], "gui/main.py")


class Reading(Project):
    def test_what_is_read_and_left_out(self):
        with open(os.path.join(self.root, "zz_big.py"), "w") as f:
            f.write("x = 1\n" * 4000)
        with open(os.path.join(self.root, "notes.md"), "w") as f:
            f.write("not code\n")
        shown, left, code = review.pick(self.root, 3000)
        self.assertEqual((shown, left), (["main.py"], ["zz_big.py"]))
        self.assertIn("  16         if hasattr(self.root, 'show_view'):", code)
        self.assertIn("card game", review.asked(self.root))

    def test_the_prompt_names_the_start_and_the_pass(self):
        p = review.prompt("beginning", "a game", "=== main.py ===", "run.sh")
        self.assertIn("Follow the program from run.sh forward", p)
        self.assertIn("### file:line", p)
        self.assertTrue(p.endswith("=== main.py ==="))
        p = review.prompt("end", "a game", "=== main.py ===", "run.sh", ["gui/deck_builder.py", "gui/utils.py"])
        self.assertIn("not shown here for room: gui/deck_builder.py, gui/utils.py. They exist", p)

    def test_who_wrote_it(self):
        with open(os.path.join(self.root, ".cinminai", "changelog.jsonl"), "w") as f:
            for model in ("Qwen3.6-35B-A3B Q4_K_M (experts in RAM)", "Qwen3.5-9B Q4_K_M",
                          "Qwen3.6-35B-A3B Q4_K_M (experts in RAM)"):
                f.write(json.dumps({"file": "main.py", "model": model}) + "\n")
        got = review.writers(self.root, ["main.py"])
        self.assertEqual(got["Qwen3.6-35B-A3B Q4_K_M (experts in RAM)"], 2)
        self.assertTrue(review.same_model("Qwen3.6-35B-A3B Q4_K_M (experts in RAM)", "Qwen3.6-35B-A3B Q4_K_M"))
        self.assertFalse(review.same_model("Qwen3.5-9B Q4_K_M", "Qwen3.6-35B-A3B Q4_K_M"))


class Run(Project):
    def test_three_passes_merged_and_checked(self):
        answers = iter([ANSWER, AGAIN, "Nothing more.\nVerdict: not done"])
        asked = []

        def chat(messages, **kw):
            asked.append(messages[0]["content"])
            self.assertTrue(kw["think"])
            return next(answers), {}
        with mock.patch.object(review, "start", lambda root: {"entry": "main.py", "started": True, "code": 124,
                                                              "out": ""}):
            got = review.run(self.root, chat, {"model": "Reviewer", "context": 24576}, say=lambda s: None)
        self.assertEqual(len(asked), 3)
        self.assertIn("starting from the end", asked[1])
        self.assertIn("in operation", asked[2])
        self.assertEqual(got["verdicts"], {"beginning": "not done", "end": "done", "operation": "not done"})
        self.assertEqual(len(got["dropped"]), 4)  # syntax, name, launch crash, no such file
        self.assertEqual(got["findings"][0]["passes"], ["beginning", "end"])  # found twice: first
        path = review.save(self.root, got)
        self.assertTrue(path.startswith(os.path.join(self.root, ".cinminai", "reviews")))
        text = review.handover(got["findings"])
        self.assertIn("main.py:16", text)
        self.assertIn("a review can be wrong", text)

    def test_a_program_that_stops_at_once_is_said_even_unasked(self):
        with mock.patch.object(review, "start", lambda root: {"entry": "main.py", "started": False, "code": 1,
                                                              "out": "Traceback: boom"}):
            got = review.run(self.root, lambda m, **kw: ("Verdict: done", {}), {"model": "R", "context": 24576},
                             say=lambda s: None)
        self.assertEqual(got["findings"][0]["state"], "checked")
        self.assertIn("stops as soon as it starts", got["findings"][0]["wrong"])

    def test_a_stop_at_start_isnt_hidden_by_another_checked_finding(self):
        """2026-10-25: a "fails on startup" checked by the import test hid that run.sh stopped (CMake missing)."""
        said = "### main.py:2\nquote: import tkinter as tk\nwrong: `tkinter` is not installed, so it fails on startup.\nsees: x\n"
        with mock.patch.object(review, "start", lambda root: {"entry": "run.sh", "started": False, "code": 1,
                                                              "out": "Error: CMake is not installed"}), \
                mock.patch.object(review, "importable", lambda root, m: False):
            got = review.run(self.root, lambda m, **kw: (said, {}), {"model": "R", "context": 24576},
                             say=lambda s: None)
        self.assertEqual([f["passes"] for f in got["findings"]][:1], [["start"]])
        self.assertIn("CMake", got["findings"][0]["sees"])


class Job(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        self.store = ModelStore(os.path.join(d, "models"))
        os.makedirs(self.store.root, exist_ok=True)
        self.guide = os.path.join(d, matcher.CATALOG["help"][0].file)
        open(self.guide, "wb").close()
        p = mock.patch.object(matcher, "read_machine", lambda **kw: machine())
        p.start()
        self.addCleanup(p.stop)

    def review_job(self):
        return next(j for j in jobs.view(self.store, self.guide)["jobs"] if j["job"] == "review")

    def test_ours_is_the_35b_and_never_the_guide(self):
        job = self.review_job()
        self.assertTrue(job["active"])
        self.assertIsNone(job["current"])  # nothing here reviews: the guide doesn't
        self.assertIn("No model", words.job_lines(job, "en")[1])
        open(self.store.path(BIG), "wb").close()
        self.assertEqual(self.review_job()["current"]["file"], BIG)  # the 27B when the 35B isn't here
        moe = "Qwen3.6-35B-A3B-Q4_K_M.gguf"
        open(self.store.path(moe), "wb").close()
        self.assertEqual(self.review_job()["current"]["file"], moe)
        self.assertEqual(jobs.context("review"), jobs.REVIEW_CONTEXT)

    def test_chosen_in_models(self):
        open(self.store.path(BIG), "wb").close()
        jobs.assign(self.store, "review", BIG, self.guide)
        plan = self.store.in_use("review")
        self.assertEqual((plan["file"], plan["context"]), (BIG, jobs.REVIEW_CONTEXT))
        self.assertEqual(jobs.assign(self.store, "review", "", self.guide)["file"], BIG)


class Words(unittest.TestCase):
    def test_no_model_in_six_languages(self):
        for lang in ("en", "es", "pt", "fr", "de", "ja"):
            self.assertTrue(words.t("m_none", lang))
            self.assertNotEqual(words.t("m_none", lang), words.t("m_none", "en") if lang != "en" else "")


if __name__ == "__main__":
    unittest.main()
