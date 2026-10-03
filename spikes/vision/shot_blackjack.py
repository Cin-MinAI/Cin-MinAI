# SPDX-License-Identifier: GPL-3.0-or-later
"""A headless screenshot of the blackjack game mid-hand (run with the project's .venv python)."""
import importlib
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
root = os.path.expanduser("~/aicui-test")
sys.path.insert(0, root)
os.chdir(root)
import pygame  # noqa: E402

ui_mod = importlib.import_module("Blackjack Game.pygame_ui")
ui = ui_mod.PygameBlackjackUI()
try:
    ui._deal()  # place the slider's bet and deal, as the DEAL button does
except Exception as e:  # still worth a picture of the table
    print("deal failed:", e)
for _ in range(3):
    ui._render()
    pygame.display.flip()
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/blackjack.png"
pygame.image.save(ui.screen, out)
print("saved", out, ui.screen.get_size())
