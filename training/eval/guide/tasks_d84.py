# SPDX-License-Identifier: CC-BY-SA-4.0
"""D84 coverage tasks: one per new help card, in every language its names exist in (PLAN D84, D25).

A card counts as covered once the base guide (the 4B on the ISO) passes its task here. The cards are read from
training/kb/transition.py, so a task always tests the card as it ships.

    python3 run_eval.py --prompt v2.2 --tasks tasks_d84.py --url ...
"""

import importlib.util
import os

from tasks import BRANDS, NO_CMD, STEPS  # noqa: F401  (run_eval loads BRANDS from the tasks file)

_spec = importlib.util.spec_from_file_location(
    "transition", os.path.join(os.path.dirname(__file__), "..", "..", "kb", "transition.py"))
_kb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_kb)
CARD = {t["id"]: t["card"] for t in _kb.TOPICS}

# The names inside programs ({ui_…}) are Mint's own, from its catalogues (labels.json "ui"): a made-up translation
# fails. The warnings must reach the reply in every language (the first run's "how do I" replies dropped them)
WARN_ERASE = ("~(?i)eras|wipe|delet|everything on|borra|todo lo|apag|tudo|effac|tout ce|lösch|alles|消去|消え|削除|"
              "すべて|全て")
WARN_HIDDEN = ("~(?i)(don.t|do not|never) (delete|change)|careful|no (borre|elimine|cambie|los borre)|cuidado|"
               "não (apague|exclua|altere)|ne (les )?(supprimez|modifiez)|attention|nicht (löschen|ändern)|vorsicht|"
               "削除しない|変更しない|注意")

TASKS = [
    {"id": "D84-01", "cat": "transition",
     "q": {"en": "How do I set up a VPN? My VPN company gave me an .ovpn file.",
           "es": "¿Cómo configuro una VPN? Mi proveedor de VPN me dio un archivo .ovpn.",
           "pt": "Como eu configuro uma VPN? Meu provedor de VPN me deu um arquivo .ovpn.",
           "fr": "Comment configurer un VPN ? Mon fournisseur VPN m'a donné un fichier .ovpn.",
           "de": "Wie richte ich ein VPN ein? Mein VPN-Anbieter hat mir eine .ovpn-Datei gegeben.",
           "ja": "VPNはどうやって設定しますか？VPN会社から.ovpnファイルをもらいました。"},
     "expect": [{"tool": "lookup_help"}, {"tool": "open_app", "args": {"app": ["network"]}}],
     "card": CARD["vpn"],
     "must": [["{network}"], ["~(?i)import"]], "must_not": NO_CMD, **STEPS},
    {"id": "D84-02", "cat": "transition",
     "q": {"en": "A window keeps asking for my keyring password. What is that?",
           "es": "Una ventana me sigue pidiendo la contraseña del llavero. ¿Qué es eso?",
           "pt": "Uma janela fica pedindo a senha do chaveiro. O que é isso?",
           "fr": "Une fenêtre me demande sans arrêt le mot de passe du trousseau. Qu'est-ce que c'est ?",
           "de": "Ein Fenster fragt ständig nach meinem Schlüsselbund-Passwort. Was ist das?"},
     "expect": [{"tool": "lookup_help"}],
     "card": CARD["keyring"],
     "must": [["{passwords_keys}"]], "must_not": NO_CMD},
    {"id": "D84-03", "cat": "transition",
     "q": {"en": "How do I see hidden files? On Windows I ticked 'Hidden items' in Explorer.",
           "es": "¿Cómo veo los archivos ocultos? En Windows marcaba 'Elementos ocultos' en el Explorador.",
           "pt": "Como vejo arquivos ocultos? No Windows eu marcava 'Itens ocultos' no Explorador.",
           "fr": "Comment voir les fichiers cachés ? Sous Windows je cochais « Éléments masqués » dans l'Explorateur.",
           "de": "Wie sehe ich versteckte Dateien? Unter Windows habe ich im Explorer 'Ausgeblendete Elemente' angehakt.",
           "ja": "隠しファイルはどうやって見ますか？Windowsではエクスプローラーで「隠しファイル」にチェックしていました。"},
     "expect": [{"tool": "lookup_help"}, {"tool": "open_app", "args": {"app": ["files"]}}],
     "card": CARD["hidden_files"],
     # "Ctrl+H", or in Japanese 「Ctrl」キーと「H」キー (the first run's correct reply failed a stricter pattern)
     "must": [["{files}"], ["~(?i)ctrl[^a-z0-9]{0,12}h(?![a-z])"], [WARN_HIDDEN]], "must_not": NO_CMD},
    {"id": "D84-04", "cat": "transition",
     "q": {"en": "How do I make a separate account for my daughter?",
           "es": "¿Cómo creo una cuenta aparte para mi hija?",
           "pt": "Como eu crio uma conta separada para minha filha?",
           "fr": "Comment créer un compte séparé pour ma fille ?",
           "de": "Wie lege ich ein eigenes Konto für meine Tochter an?",
           "ja": "娘のために別のアカウントを作るにはどうすればいいですか？"},
     "expect": [{"tool": "lookup_help"}, {"tool": "open_app", "args": {"app": ["users"]}}],
     "card": CARD["user_accounts"],
     "must": [["{users}"], ["{ui_no_password_set}"]], "must_not": NO_CMD, **STEPS},
    {"id": "D84-05", "cat": "transition",
     "q": {"en": "How do I make a bootable USB stick from an ISO? On Windows I used Rufus.",
           "es": "¿Cómo hago un USB de arranque con una ISO? En Windows usaba Rufus.",
           "pt": "Como faço um pendrive bootável a partir de uma ISO? No Windows eu usava o Rufus.",
           "fr": "Comment créer une clé USB bootable à partir d'un ISO ? Sous Windows j'utilisais Rufus.",
           "de": "Wie erstelle ich einen bootfähigen USB-Stick aus einer ISO? Unter Windows habe ich Rufus benutzt.",
           "ja": "ISOから起動できるUSBメモリを作るには？WindowsではRufusを使っていました。"},
     "expect": [{"tool": "lookup_help"}, {"tool": "open_app", "args": {"app": ["usb_writer"]}}],
     "card": CARD["bootable_usb"],
     "must": [["{usb_writer}"], ["{ui_select_image}"], [WARN_ERASE]], "must_not": NO_CMD, **STEPS},
    {"id": "D84-06", "cat": "transition",
     "q": {"en": "Is there something like VS Code here for coding with AI?"},
     "expect": [{"tool": "lookup_help"}],
     "card": CARD["aicui"],
     "must": [["AICUI"]], "must_not": NO_CMD},
    # "What is…?" (D84 part 1): Ian's everyday picture has to come through, not only the steps
    {"id": "D84-07", "cat": "transition",
     "q": {"en": "What is a VPN, and do I need one?"},
     "expect": [{"tool": "lookup_help"}],
     "card": CARD["vpn"],
     "must": [["~(?i)po box|post office|mailbox"], ["~(?i)anonymous|authorit"]], "must_not": NO_CMD},
    {"id": "D84-08", "cat": "transition",
     "q": {"en": "What is a keyring on Linux?"},
     "expect": [{"tool": "lookup_help"}],
     "card": CARD["keyring"],
     "must": [["~(?i)locked box|vault|unlocks? the keys"]], "must_not": NO_CMD},
    {"id": "D84-09", "cat": "transition",
     "q": {"en": "Why can't I just copy the ISO file onto the USB stick?"},
     "expect": [{"tool": "lookup_help"}],
     "card": CARD["bootable_usb"],
     "must": [["~(?i)\\bimage\\b"], ["~(?i)\\bmap\\b|every bit|bits"]], "must_not": NO_CMD},
]
