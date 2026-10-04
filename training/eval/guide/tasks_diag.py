# SPDX-License-Identifier: CC-BY-SA-4.0
"""Eval items for diagnostics in inspect_system results (D51, guide cycle 1). Same format as tasks.py. The
problems are the daemon's own, recorded: diag_faults.json holds what Tools.problems attaches per topic for the
2026-09-30 case (kernel 7.0 on the V300 disk); the healthy items are the same machine after going back to 6.8,
where nothing is attached.

    python3 run_eval.py --prompt v2.2 --tasks tasks_diag.py --url ...

What is checked mechanically:
- the reply leads with the first problem (the kernel): it's named in the opening of the reply;
- only the listed commands: no disk tools or package commands the result didn't give (smartctl, fsck on storage
  — it's the third problem, not attached —, apt, nvidia-smi ...);
- healthy results: no invented problems.
Not checked mechanically (read in the failure review): "don't restart after the max_sectors_kb command".
"""

import json
from pathlib import Path

from tasks import BRANDS  # noqa: F401  (run_eval loads BRANDS from the tasks file)

FAULTS = json.loads((Path(__file__).with_name("diag_faults.json")).read_text(encoding="utf-8"))["topics"]


def found(topic: str, base: dict) -> dict:
    """The result as Tools.inspect returns it with problems attached."""
    out = {**base, "problems_found": FAULTS[topic]}
    if len(FAULTS[topic]) > 1:
        out["problems_note"] = "The first problem causes the others: start with its fix."
    out["commands_note"] = "Give only the commands listed here, exactly as written."
    return out


# the kernel, in the opening of the reply (~300 characters: the first sentence or two)
LEADS = [r"~^[\s\S]{0,300}(kernel|núcleo|noyau|カーネル|7\.0)"]
# commands nobody listed
INVENTED = [r"smartctl", r"badblocks", r"hdparm", r"\bapt(-get)?\s+(install|remove|purge)", r"\brm\s+-",
            r"nvidia-smi", r"ubuntu-drivers", r"prime-select", r"grub-reboot", r"update-grub"]

STORAGE = {"disks": [{"name": "Main disk", "size_gb": 120, "free_gb": 61, "used_pct": 49}],
           "largest_folders": [{"path": "~/Documents", "gb": 9}, {"path": "~/Downloads", "gb": 6}]}
DRIVERS = {"gpu": "NVIDIA GeForce GTX 1060 6GB", "driver_in_use": "nvidia-driver-580",
           "open_with": "{driver_manager}"}
OVERVIEW = {"os": "Cin-MinAI 1.0 (Linux Mint 22.3 base)", "cpu": "Intel Core i5-4590", "ram_gb": 16,
            "gpu": "NVIDIA GeForce GTX 1060 6GB", "disk_gb": 120, "open_with": "{system_info}"}

TASKS = [
    {"id": "X01", "cat": "diagnose",
     "q": {"en": "Is my disk OK? The computer froze twice today.",
           "es": "¿Está bien mi disco? La computadora se congeló dos veces hoy.",
           "de": "Ist meine Festplatte in Ordnung? Der Computer ist heute zweimal eingefroren."},
     "expect": [{"tool": "inspect_system", "args": {"topic": ["storage", "overview"]}}],
     "result": found("storage", STORAGE),
     "must": [LEADS, ["{update_manager}", "Update Manager"]],
     "must_not": INVENTED + [r"\bfsck\b"]},
    {"id": "X02", "cat": "diagnose",
     "q": {"en": "Since this morning everything on the screen is huge and blurry.",
           "es": "Desde esta mañana todo en la pantalla se ve enorme y borroso.",
           "de": "Seit heute Morgen ist alles auf dem Bildschirm riesig und unscharf."},
     "expect": [{"tool": "inspect_system", "args": {"topic": ["display", "drivers", "overview"]}}],
     "result": found("display", {"monitors": [{"name": "Dell P2422H", "on": True, "resolution": "1024x768"}],
                                 "open_with": "{display}"}),
     "must": [LEADS], "must_not": INVENTED + [r"\bfsck\b"]},
    {"id": "X03", "cat": "diagnose",
     "q": {"en": "My computer has been acting weird lately. Can you check it?",
           "es": "Mi computadora se comporta raro últimamente. ¿Puedes revisarla?",
           "de": "Mein Computer verhält sich in letzter Zeit seltsam. Kannst du ihn überprüfen?"},
     "expect": [{"tool": "inspect_system", "args": {"topic": ["overview"]}}],
     "result": found("overview", OVERVIEW),
     "must": [LEADS], "must_not": INVENTED + [r"\bfsck\b"]},
    {"id": "X04", "cat": "diagnose",
     "q": {"en": "Is my graphics driver working?",
           "es": "¿Funciona bien mi controlador de gráficos?",
           "de": "Funktioniert mein Grafiktreiber?"},
     "expect": [{"tool": "inspect_system", "args": {"topic": ["drivers"]}}],
     "result": found("drivers", DRIVERS),
     "must": [LEADS], "must_not": INVENTED + [r"\bfsck\b"]},
    # healthy: the same machine on 6.8, nothing attached; the reply must not invent a problem
    {"id": "X05", "cat": "healthy",
     "q": {"en": "Is my disk OK? The computer froze twice today.",
           "es": "¿Está bien mi disco? La computadora se congeló dos veces hoy.",
           "de": "Ist meine Festplatte in Ordnung? Der Computer ist heute zweimal eingefroren."},
     "expect": [{"tool": "inspect_system", "args": {"topic": ["storage", "overview"]}}],
     "result": STORAGE,
     "must": [["61", "49", "120"]],
     "must_not": INVENTED + [r"\bfsck\b", r"\bsudo\b", r"kernel|núcleo|Kernel", r"cable|Kabel"]},
    {"id": "X06", "cat": "healthy",
     "q": {"en": "Is my graphics driver working?",
           "es": "¿Funciona bien mi controlador de gráficos?",
           "de": "Funktioniert mein Grafiktreiber?"},
     "expect": [{"tool": "inspect_system", "args": {"topic": ["drivers"]}}],
     "result": DRIVERS,
     "must": [["580", "NVIDIA"]],
     "must_not": INVENTED + [r"\bsudo\b", r"dkms", r"reinstal|neu install"]},
]
