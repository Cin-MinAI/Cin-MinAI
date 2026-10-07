# SPDX-License-Identifier: GPL-3.0-or-later
"""lookup_help retrieval, measured on labelled queries (tests/data/lookup_queries.jsonl):

- "sessions": the queries the teacher wrote in the session corpus, with the card it was given (511);
- "eval-HO": the queries the shipped guide itself wrote on the public eval, with the card that task
  needs (80);
- "heldout-HO": the shipped guide's queries on the held-out eval (47), labelled by hand from the query
  alone (a list = either card is right; null = no card fits: rename a file, undo, select several files,
  write a letter). **The clean test:** the first two sets were used to write the search words; this
  one was labelled and measured once, after that (2026-09-28: 78.7 %, 37/47), and must not be tuned on.

    python3 -m unittest tests.unit.test_helpcards -v        (from the repo root)
    python3 tests/unit/test_helpcards.py --report            (accuracy per set and language, the misses)
"""

import collections
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "distro", "packages", "cinminai-daemon"))

from cin_minai.daemon.helpcards import HelpIndex, resolve, tokens  # noqa: E402
import gen_data  # noqa: E402

QUERIES = [json.loads(l) for l in open(os.path.join(ROOT, "tests", "data", "lookup_queries.jsonl"), encoding="utf-8")]
# Floors, set just under what was measured (2026-09-28); a change to the index or the search words that
# drops below them fails. Raise them as retrieval improves.
FLOOR = {"sessions": 0.90, "eval-HO": 0.95, "heldout-HO": 0.75}

_DATA = None


def data() -> dict:
    global _DATA
    if _DATA is None:
        _DATA = gen_data.build(ROOT)
    return _DATA


def accuracy(index: HelpIndex, rows: list) -> tuple[float, list]:
    misses = []
    for r in rows:
        got, _ = index.lookup(r["q"], r["lang"])
        want = r["id"] if isinstance(r["id"], list) else [r["id"]]
        if got not in want:
            misses.append((r, got))
    return 1 - len(misses) / len(rows), misses


class HelpCards(unittest.TestCase):
    def setUp(self):
        self.index = HelpIndex(data()["help.json"])

    def test_accuracy(self):
        for src, floor in FLOOR.items():
            acc, _ = accuracy(self.index, [r for r in QUERIES if r["src"] == src])
            self.assertGreaterEqual(acc, floor, f"{src}: {acc:.1%}")

    def test_every_card_findable_by_its_windows_name(self):
        for c in data()["help.json"]["cards"]:
            self.assertEqual(self.index.lookup(c["windows"], "en")[0], c["id"], c["windows"])

    def test_writing_a_document_finds_the_office_card(self):
        # boot check 1 (2026-09-28): a real query went to the word-count card
        for q, lang in [("open a program to write a document in", "en"), ("program to write a letter", "en"),
                        ("escribir un documento", "es"), ("Dokument schreiben", "de")]:
            self.assertEqual(self.index.lookup(q, lang)[0], "office", q)
        self.assertEqual(self.index.lookup("count the words in my document", "en")[0], "word_count")

    def test_d84_batch_1_found_in_six_languages(self):
        # D84 (2026-10-06): the first coverage cards, asked the way people ask, one question per language
        asked = {
            "vpn": ["how do I set up a VPN", "cómo configurar una VPN", "como configurar uma VPN",
                    "comment configurer un VPN", "wie richte ich ein VPN ein", "VPNを設定する方法"],
            "keyring": ["it keeps asking for my keyring password", "me pide la contraseña del llavero",
                        "pede a senha do chaveiro", "il demande le mot de passe du trousseau",
                        "Schlüsselbund Passwort wird abgefragt", "キーリングのパスワードを聞かれる"],
            "hidden_files": ["how do I show hidden files", "cómo ver archivos ocultos", "como ver arquivos ocultos",
                             "afficher les fichiers cachés", "versteckte Dateien anzeigen", "隠しファイルを表示する"],
            "user_accounts": ["add an account for my daughter", "crear una cuenta de usuario para mi hijo",
                              "criar uma conta de usuário para minha filha", "créer un compte pour mon fils",
                              "neues Benutzerkonto für meine Tochter", "子供用のユーザーアカウントを作る"],
            "bootable_usb": ["make a bootable USB from an ISO like Rufus", "crear un USB booteable con una ISO",
                             "criar pendrive bootável com ISO", "créer une clé USB bootable avec un ISO",
                             "bootfähigen USB-Stick aus ISO erstellen", "ISOから起動用USBを作る"],
            "aicui": ["is there something like VS Code for coding with AI", "un editor de código para programar con IA",
                      "ambiente de desenvolvimento para programar com IA",
                      "un éditeur de code pour programmer avec l'IA", "Entwicklungsumgebung zum Programmieren mit KI",
                      "AIでプログラミングする開発環境"],
        }
        for card, questions in asked.items():
            for lang, q in zip(["en", "es", "pt", "fr", "de", "ja"], questions):
                self.assertEqual(self.index.lookup(q, lang)[0], card, q)

    def test_d84_batch_2_found_in_six_languages(self):
        asked = {
            "usb_format": ["how do I format a USB stick", "cómo formatear una memoria USB", "como formatar um pendrive",
                           "comment formater une clé USB", "wie formatiere ich einen USB-Stick",
                           "USBメモリをフォーマットする方法"],
            "software_sources": ["is it safe to add a PPA", "qué es un repositorio de software", "o que é um repositório",
                                 "comment changer de miroir de téléchargement", "Paketquellen ändern",
                                 "ソフトウェアのリポジトリとは"],
            "panel": ["how do I pin a program to the taskbar", "cómo anclar un programa a la barra de tareas",
                      "como fixar um programa na barra de tarefas", "épingler un programme à la barre des tâches",
                      "Programm an die Taskleiste anheften", "タスクバーにプログラムをピン留めする"],
            "online_accounts": ["add my Google account to the calendar", "añadir mi cuenta de Google",
                                "adicionar minha conta Google", "ajouter mon compte Google", "Google-Konto hinzufügen",
                                "グーグルアカウントを追加する"],
            "notifications": ["turn off notifications", "desactivar las notificaciones", "desativar as notificações",
                              "désactiver les notifications", "Benachrichtigungen ausschalten", "通知をオフにする"],
            "auto_login": ["log in automatically without a password", "inicio de sesión automático",
                           "login automático sem senha", "connexion automatique sans mot de passe",
                           "automatische Anmeldung einschalten", "自動ログインを設定する"],
            "disk_health": ["is my hard drive dying", "salud del disco duro", "saúde do disco rígido",
                            "santé du disque dur", "Festplatte Zustand prüfen", "ディスクの健康状態を確認する"],
            "specs": ["how much RAM do I have", "qué procesador tengo", "quanta memória RAM eu tenho",
                      "quelle carte graphique j'ai", "welche Grafikkarte habe ich", "メモリはどのくらいありますか"],
            "battery": ["my laptop battery drains fast", "la batería del portátil", "a bateria do notebook",
                        "la batterie de mon portable", "Akku vom Laptop", "ノートパソコンのバッテリー"],
            "live_usb": ["can I try it without installing", "probar sin instalar", "testar sem instalar",
                         "essayer sans installer", "ohne Installation testen", "インストールせずにお試しできますか"],
        }
        for card, questions in asked.items():
            for lang, q in zip(["en", "es", "pt", "fr", "de", "ja"], questions):
                self.assertEqual(self.index.lookup(q, lang)[0], card, q)

    def test_hands_on_round_1_found_in_six_languages(self):
        # the test-SSD round (2026-10-07): "scan for malware" found the Document Scanner card, and three questions had
        # no card at all. ("how much RAM am I using" and "… do I have" are the same words to the search; both are the
        # memory system check's to answer.)
        asked = {
            "admin_account": ["is this an admin account", "¿es esta una cuenta de administrador?", "sou administrador?",
                              "suis-je administrateur ?", "bin ich Administrator?", "管理者アカウントですか"],
            "memory_use": ["RAM usage right now", "cuánta memoria RAM estoy usando", "quanta memória estou usando",
                           "utilisation de la mémoire", "Arbeitsspeicher Auslastung", "メモリ使用量を確認したい"],
            "temperatures": ["how hot is my CPU", "temperatura de la CPU", "temperatura do processador",
                             "température du processeur", "CPU Temperatur anzeigen", "CPUの温度を知りたい"],
            "antivirus": ["how do I scan for malware", "escanear malware", "escanear vírus", "analyser les malwares",
                          "nach Malware scannen", "マルウェアをスキャンしたい"],
        }
        for card, questions in asked.items():
            for lang, q in zip(["en", "es", "pt", "fr", "de", "ja"], questions):
                self.assertEqual(self.index.lookup(q, lang)[0], card, q)

    def test_no_match(self):
        self.assertEqual(self.index.lookup("the the and of", "en"), (None, "Nothing in the built-in help matches this."))

    def test_names_in_the_users_language(self):
        cid, text = self.index.lookup("Logithèque installer programme", "fr")
        self.assertEqual(cid, "install")
        self.assertIn("Logithèque", text)
        self.assertNotIn("{", text)

    def test_tokens(self):
        self.assertEqual(tokens("Installer un programme"), ["insta", "progr"])
        self.assertEqual(tokens("日本語"), ["日本", "本語"])
        self.assertEqual(resolve("{files}", {"files": {"en": "Files"}}, "ja"), "Files")


def report() -> None:
    index = HelpIndex(data()["help.json"])
    for src in FLOOR:
        rows = [r for r in QUERIES if r["src"] == src]
        acc, misses = accuracy(index, rows)
        by = collections.defaultdict(list)
        for r in rows:
            by[r["lang"]].append(r)
        langs = "  ".join(f"{l} {accuracy(index, rs)[0]:.0%}" for l, rs in sorted(by.items()))
        print(f"{src}: {acc:.1%} of {len(rows)}   {langs}")
        for r, got in misses:
            print(f"   {r['lang']} want {str(r['id']):<17} got {str(got):<17} | {r['q']}")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        unittest.main()
