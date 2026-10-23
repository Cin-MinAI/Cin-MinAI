# SPDX-License-Identifier: CC-BY-SA-4.0
"""Eval items asked in the middle of a conversation (2026-10-23). Asked alone, prompt v2.6 sent Ian's questions to
Wikipedia (12 of 14); on the NVMe, after earlier questions the help had answered, the same questions went to the help.
Each item here comes after `history`: earlier turns in the daemon's own shape (the user's message, the tool call, "Result
of <tool>:" with the real help card and the style line, the reply), so stage A measures the pull of the earlier calls.

    python3 run_eval.py --prompt v2.7 --tasks tasks_conversation.py --url ...
"""

from tasks import BRANDS  # noqa: F401  (run_eval loads BRANDS from the tasks file)

INSTALL = ("How do I install a program?", "lookup_help", {"query": "install a program"},
           "Installing programs: open the Menu (bottom-left, or press the Windows key), open Software Manager, type the "
           "program's name in the search box, click it, then click Install and type your password. Windows .exe files "
           "don't run here; most popular programs have a version in Software Manager.",
           "You install programs from Software Manager.\n1. Open the Menu (bottom-left).\n2. Open Software Manager.\n"
           "3. Type the program's name in the search box and click it.\n4. Click Install and type your password.")
DOWNLOADS = ("Where do my downloads go?", "lookup_help", {"query": "where do downloads go"},
             "Downloads: files from the web go to the Downloads folder. Open Files and click Downloads in the left "
             "column. In Firefox Web Browser you can also click the arrow icon at the top-right to see recent downloads.",
             "Files from the web go to the Downloads folder.\n1. Open Files.\n2. Click Downloads in the left column.")
CURIE = ("Who was Marie Curie?", "wikipedia", {"title": "Marie Curie"}, "[1] Marie Curie",
         "Marie Curie was a physicist and chemist who did pioneering research on radioactivity [1]. She was the first "
         "woman to win a Nobel Prize, and the only person to win Nobel Prizes in two sciences [1].")

# Ian's turn before the coral snake (NVMe, 2026-10-23): a subject sent to the help, a stray word's card back
TRANSISTOR = ("What does a transistor look like?", "lookup_help", {"query": "transistor appearance"}, DOWNLOADS[3],
              "Downloads: files from the web go to the Downloads folder. Open Files and click Downloads in the left "
              "column. In Firefox Web Browser you can also click the arrow icon at the top-right to see recent downloads.")

def helped(q, query, card, reply):
    return (q, "lookup_help", {"query": query}, card, reply)


WIFI = helped("How do I connect to wifi?", "connect to wifi",
              "Wi-Fi: click the network icon in the panel (bottom-right, next to the clock). Click your network's name, "
              "type the Wi-Fi password, and click Connect. It connects by itself next time. More options are in Network "
              "in System Settings.",
              "1. Click the network icon in the panel (bottom-right).\n2. Click your network's name.\n3. Type the Wi-Fi "
              "password and click Connect.")
UPDATES = helped("How do I update the computer?", "update the computer",
                 "Updates: Update Manager does what Windows Update does. When updates are ready, its shield icon in the "
                 "panel (bottom-right) shows a dot. Click it, then click Install Updates and type your password. It never "
                 "restarts the computer by itself; it tells you if a restart is needed.",
                 "Update Manager does what Windows Update did.\n1. Click the shield icon in the panel.\n2. Click Install "
                 "Updates and type your password.")
WALLPAPER = helped("How do I change the wallpaper?", "change the wallpaper",
                   "Wallpaper: right-click an empty spot on the desktop and choose Change Desktop Background. That opens "
                   "Backgrounds. Click a picture to use it; use the + button to add your own pictures folder.",
                   "1. Right-click an empty spot on the desktop.\n2. Choose Change Desktop Background.\n3. Click a picture.")
PRINTERS = helped("How do I set up a printer?", "printer setup",
                  "Printers: most USB and network printers are found by themselves. If yours isn't, open Printers from the "
                  "Menu, click Add, choose your printer from the list, and click Forward to finish.",
                  "Most printers are found by themselves. If yours isn't:\n1. Open Printers from the Menu.\n2. Click Add.\n"
                  "3. Choose your printer and click Forward.")
TEXT = helped("Can I make the text bigger?", "make text bigger",
              "Bigger text everywhere: open Font Selection in System Settings and raise Text scaling factor (for example "
              "to 1.2). Or switch on Large text in Accessibility. In Firefox, Ctrl and + zooms.",
              "1. Open Font Selection in System Settings.\n2. Raise Text scaling factor, for example to 1.2.")
COMPUTER = [INSTALL, DOWNLOADS, WIFI, UPDATES, WALLPAPER, PRINTERS, TEXT]

AFTER_HELP = [INSTALL, DOWNLOADS]  # two computer questions, both answered from the help
AFTER_BOTH = [INSTALL, CURIE, DOWNLOADS]  # a subject in between, the help last
AFTER_MISROUTE = [INSTALL, TRANSISTOR]  # one subject already sent to the help
# a long talk (Ian's coral snake was the 24th request since the daemon started) and the most the guide keeps now
# (history_turns 8: past it, back to the last 4)
LONG_20 = (COMPUTER * 3)[:19] + [TRANSISTOR]
LONG_8 = LONG_20[-8:]

# Ian's second talk on the NVMe (2026-10-23, watched): two Wikipedia answers, then the web for the Cuban Missile Crisis,
# and from there every subject went to the web. Kept the old way ("before": a Wikipedia answer with no call to see) and
# the way guide.py keeps it now (every turn its call and result).
ROME_SPLIT = ("When did Rome split into 2 empires?", "wikipedia", {"title": "Fall of the Western Roman Empire"},
              "[1] Fall of the Western Roman Empire",
              "The provided pages do not answer the question. They only discuss the fall of the Western Roman Empire, "
              "not when Rome split into two empires.")
ROME_FALL = ("When did the Western Roman Empire fall?", "wikipedia", {"title": "Fall of the Western Roman Empire"},
             "[1] Fall of the Western Roman Empire",
             "The Western Roman Empire fell in 476. This is when the Germanic king Odoacer deposed the last emperor, "
             "Romulus Augustulus.")
CUBA = ("Why did the Cuban Missile Crisis happen?", "web_search", {"query": "Why did the Cuban Missile Crisis happen?"},
        "[1] WHY | English meaning - Cambridge Dictionary\n[2] Cuban Missile Crisis | Britannica\n[3] Cuban Missile Crisis",
        "The Cuban Missile Crisis happened because the Soviet Union placed nuclear missiles in Cuba, bringing the U.S. "
        "and the Soviet Union to the brink of war in October 1962 [2].")
ANACONDA = ("Whats an anaconda look like?", "web_search", {"query": "What does an anaconda look like?"},
            "[1] Anaconda | Size, Diet, & Facts | Britannica\n[2] Anaconda - Wikipedia\n[3] Green anaconda",
            "Anacondas are large, constricting, water-loving snakes found in tropical South America [1].")
IAN_TALK = [ROME_SPLIT, ROME_FALL, CUBA, ANACONDA]
IAN_TALK_BEFORE = [t + ("before",) for t in IAN_TALK]
IAN_TALK_PLAIN = [t + ("plain",) for t in IAN_TALK]
LONG_20_PLAIN = [t + ("plain",) for t in LONG_20]
# how much of the talk the choice needs: the last turn or two, plain
IAN_LAST1, IAN_LAST2, LONG_LAST2 = IAN_TALK_PLAIN[-1:], IAN_TALK_PLAIN[-2:], LONG_20_PLAIN[-2:]

TASKS = []
for hid, history in (("h", AFTER_HELP), ("b", AFTER_BOTH), ("m", AFTER_MISROUTE), ("L", LONG_20),
                     ("l", LONG_8), ("I", IAN_TALK), ("i", IAN_TALK_BEFORE),
                     ("P", IAN_TALK_PLAIN), ("p", LONG_20_PLAIN),
                     ("A", IAN_LAST1), ("B", IAN_LAST2), ("D", LONG_LAST2)):
    TASKS += [
        {"id": f"C01{hid}", "cat": "conversation", "history": history,
         "q": {"en": "What does a coral snake look like?"},
         "expect": [{"tool": "wikipedia", "args": {"title": "~coral"}}]},
        {"id": f"C02{hid}", "cat": "conversation", "history": history,
         "q": {"en": "Can you show a picture of a coral snake?"},
         "expect": [{"tool": "wikipedia", "args": {"title": "~coral"}}]},
        {"id": f"C03{hid}", "cat": "conversation", "history": history,
         "q": {"en": "How do you make Pho and where does it come from? Whats it normally look like?"},
         "expect": [{"tool": "wikipedia", "args": {"title": "~ph"}}]},
        {"id": f"C04{hid}", "cat": "conversation", "history": history,
         "q": {"en": "How much does the average newborn weigh?"},
         "expect": [{"tool": "wikipedia"}, {"tool": "web_search"}]},
        {"id": f"C05{hid}", "cat": "conversation", "history": history, "q": {"en": "Whats a Raspberry Pi?"},
         "expect": [{"tool": "wikipedia", "args": {"title": "~raspberry"}}]},
        {"id": f"C06{hid}", "cat": "conversation", "history": history, "q": {"en": "What does a transistor look like?"},
         "expect": [{"tool": "wikipedia", "args": {"title": "~transistor"}}]},
        {"id": f"C07{hid}", "cat": "conversation", "history": history,
         "q": {"en": "Whats th Golden Gate Bridge look like? How long is it?"},
         "expect": [{"tool": "wikipedia", "args": {"title": "~golden"}}]},
        # and the computer is still the computer's after a subject
        {"id": f"C08{hid}", "cat": "conversation", "history": history, "q": {"en": "How do I set up my printer?"},
         "expect": [{"tool": "lookup_help"}]},
        {"id": f"C09{hid}", "cat": "conversation", "history": history, "q": {"en": "Where did the earthworm originate?"},
         "expect": [{"tool": "wikipedia", "args": {"title": "~earthworm"}}]},
        {"id": f"C10{hid}", "cat": "conversation", "history": history, "q": {"en": "Where is Reykjavik?"},
         "expect": [{"tool": "wikipedia", "args": {"title": "~reykjav"}}]},
    ]

# a follow-up that needs the turn before it (Ian, 2026-10-23: "Where is Reykjavik?", then "How cold does it get?")
REYKJAVIK = ("Where is Reykjavik?", "web_search", {"query": "Where is Reykjavik?"},
             "[1] Reykjavík | Iceland, History, Map, & Population | Britannica",
             "Reykjavik is located in southwestern Iceland [1]. It is the northernmost capital of a sovereign state [1].")
for hid, history in (("A", [REYKJAVIK + ("plain",)]), ("B", IAN_TALK_PLAIN[-1:] + [REYKJAVIK + ("plain",)]),
                     ("I", IAN_TALK + [REYKJAVIK])):
    TASKS.append({"id": f"F01{hid}", "cat": "followup", "history": history, "q": {"en": "How cold does it get?"},
                  "expect": [{"tool": "wikipedia", "args": {"title": "~reykjav|iceland"}},
                             {"tool": "web_search", "args": {"query": "~reykjav|iceland"}}]})
