# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep this computer offline (PLAN D28, SPEC §12.4): for the careful newcomer who doesn't trust online services.

Offline means the whole computer, not a promise from our parts: NetworkManager's networking is switched off, Wi-Fi and
cable alike (an active desktop user may do that without a password; NetworkManager remembers it across restarts). The
switch is the panel icon's menu, "Keep this computer offline"; the panel then says OFFLINE, and the assistant doesn't
offer web searches (it says how to go online instead).

Going online is one deliberate button, "Go online to install updates": the Updates window (updates.py, D29) connects
for the check and the install and goes back offline after them. A reminder about security updates comes at most once a month, and only in offline mode.

    cinminai-offline on | off | updates | remind

Written by Claude (not a native speaker of es/pt/fr/de/ja): wants a native speaker's review (D36).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

MONTH_S = 30 * 86400
CONNECT_S = 90      # how long going online may take before it's given up
INSTALLERS = ("dpkg", "apt", "apt-get", "aptd", "synaptic", "unattended-upgr")  # an install still running

WORDS = {
    "en": {"title": "Offline", "now_offline": "This computer is offline now: Wi-Fi and cable are off. To install "
           "updates, right-click the assistant's icon in the panel and choose Go online to install updates.",
           "now_online": "This computer can go online again.",
           "done": "Back offline. Updates were last installed today.",
           "no_connection": "Couldn't get online within a minute and a half. Check the cable or the Wi-Fi, then try "
                            "again. This computer stays offline.",
           "remind": "It's been over a month since the last security updates. When you're ready, right-click the "
                     "assistant's icon in the panel and choose Go online to install updates. (A reminder at most "
                     "once a month.)",
           "assistant": "Offline mode is on, so I won't look this up on the web. To go online, right-click the "
                        "assistant's icon in the panel and switch off Keep this computer offline."},
    "es": {"title": "Sin conexión", "now_offline": "Este equipo está sin conexión: el wifi y el cable están "
           "apagados. Para instalar actualizaciones, haz clic derecho en el icono del asistente en el panel y elige "
           "Conectarse para instalar actualizaciones.",
           "now_online": "Este equipo puede volver a conectarse.",
           "done": "Sin conexión de nuevo. Las actualizaciones se instalaron hoy.",
           "no_connection": "No se pudo conectar en un minuto y medio. Revisa el cable o el wifi y vuelve a "
                            "intentarlo. El equipo sigue sin conexión.",
           "remind": "Hace más de un mes de las últimas actualizaciones de seguridad. Cuando quieras, haz clic derecho "
                     "en el icono del asistente en el panel y elige Conectarse para instalar actualizaciones. (Como "
                     "mucho un aviso al mes.)",
           "assistant": "El modo sin conexión está activado, así que no lo buscaré en la web. Para conectarte, haz "
                        "clic derecho en el icono del asistente en el panel y desactiva Mantener este equipo sin "
                        "conexión."},
    "pt": {"title": "Offline", "now_offline": "Este computador está offline: o Wi-Fi e o cabo estão desligados. Para "
           "instalar atualizações, clique com o botão direito no ícone do assistente no painel e escolha Conectar para "
           "instalar atualizações.",
           "now_online": "Este computador pode voltar a se conectar.",
           "done": "Offline de novo. As atualizações foram instaladas hoje.",
           "no_connection": "Não foi possível conectar em um minuto e meio. Verifique o cabo ou o Wi-Fi e tente de "
                            "novo. O computador continua offline.",
           "remind": "Faz mais de um mês desde as últimas atualizações de segurança. Quando quiser, clique com o botão "
                     "direito no ícone do assistente no painel e escolha Conectar para instalar atualizações. (No "
                     "máximo um aviso por mês.)",
           "assistant": "O modo offline está ligado, então não vou pesquisar isso na web. Para se conectar, clique com "
                        "o botão direito no ícone do assistente no painel e desligue Manter este computador offline."},
    "fr": {"title": "Hors ligne", "now_offline": "Cet ordinateur est hors ligne : le Wi-Fi et le câble sont coupés. "
           "Pour installer les mises à jour, faites un clic droit sur l'icône de l'assistant dans le panneau et "
           "choisissez Se connecter pour installer les mises à jour.",
           "now_online": "Cet ordinateur peut de nouveau se connecter.",
           "done": "De nouveau hors ligne. Les mises à jour ont été installées aujourd'hui.",
           "no_connection": "Impossible de se connecter en une minute et demie. Vérifiez le câble ou le Wi-Fi, puis "
                            "réessayez. L'ordinateur reste hors ligne.",
           "remind": "Les dernières mises à jour de sécurité datent de plus d'un mois. Quand vous voulez, faites un "
                     "clic droit sur l'icône de l'assistant dans le panneau et choisissez Se connecter pour installer "
                     "les mises à jour. (Un rappel par mois au plus.)",
           "assistant": "Le mode hors ligne est activé : je ne chercherai pas cela sur le web. Pour vous connecter, "
                        "faites un clic droit sur l'icône de l'assistant dans le panneau et désactivez Garder cet "
                        "ordinateur hors ligne."},
    "de": {"title": "Offline", "now_offline": "Dieser Computer ist jetzt offline: WLAN und Kabel sind aus. Um Updates "
           "zu installieren, klicken Sie mit der rechten Maustaste auf das Symbol des Assistenten in der Leiste und "
           "wählen Sie Für Updates online gehen.",
           "now_online": "Dieser Computer kann wieder online gehen.",
           "done": "Wieder offline. Die Updates wurden heute installiert.",
           "no_connection": "Innerhalb von anderthalb Minuten kam keine Verbindung zustande. Prüfen Sie Kabel oder "
                            "WLAN und versuchen Sie es erneut. Der Computer bleibt offline.",
           "remind": "Die letzten Sicherheitsupdates sind über einen Monat her. Wenn Sie so weit sind, klicken Sie mit "
                     "der rechten Maustaste auf das Symbol des Assistenten in der Leiste und wählen Sie Für Updates "
                     "online gehen. (Höchstens eine Erinnerung im Monat.)",
           "assistant": "Der Offline-Modus ist an, deshalb suche ich das nicht im Web. Um online zu gehen, klicken Sie "
                        "mit der rechten Maustaste auf das Symbol des Assistenten in der Leiste und schalten Sie Diesen "
                        "Computer offline halten aus."},
    "ja": {"title": "オフライン", "now_offline": "このコンピューターはオフラインになりました。Wi-Fiも有線も切れて"
           "います。アップデートを入れるには、パネルのアシスタントのアイコンを右クリックして「オンラインにして"
           "アップデートを入れる」を選んでください。",
           "now_online": "このコンピューターはまたオンラインにできます。",
           "done": "オフラインに戻りました。アップデートは今日入れました。",
           "no_connection": "1分半たってもオンラインになれませんでした。ケーブルかWi-Fiを確かめて、もう一度"
                            "お試しください。オフラインのままです。",
           "remind": "前回のセキュリティアップデートから1か月以上たちました。準備ができたら、パネルのアシスタントの"
                     "アイコンを右クリックして「オンラインにしてアップデートを入れる」を選んでください。（お知らせは"
                     "多くても月に1回です）",
           "assistant": "オフラインモードがオンなので、ウェブでは調べません。オンラインにするには、パネルの"
                        "アシスタントのアイコンを右クリックして「このコンピューターをオフラインに保つ」をオフに"
                        "してください。"},
}


def lang() -> str:
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        code = (os.environ.get(var) or "").split(":")[0][:2]
        if code:
            return code if code in WORDS else "en"
    return "en"


def words(key: str, code: str | None = None) -> str:
    return WORDS.get(code or lang(), WORDS["en"])[key]


def says(code: str, on_text) -> dict | None:
    """In offline mode the assistant offers nothing that goes online (no search card, hidden rather than greyed out):
    it says how to go online instead. None when the computer isn't in offline mode."""
    if not on():
        return None
    reply = words("assistant", code)
    on_text(reply)
    return {"tool": "offline", "reply": reply}


def switch_path() -> str:
    """Offline mode's switch: this file exists while the person keeps the computer offline (the panel icon makes and
    removes it, through this program)."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "cinminai", "offline-on")


def state_dir() -> str:
    return os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "cinminai")


def updated_path() -> str:
    return os.path.join(state_dir(), "offline-updated")


def reminded_path() -> str:
    return os.path.join(state_dir(), "offline-reminded")


def on() -> bool:
    return os.path.exists(switch_path())


def _stamp(path: str, now: float | None = None) -> None:
    """When it happened, as the file's time (and in it, for a person who opens it)."""
    now = now or time.time()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S\n", time.localtime(now)))
    os.utime(path, (now, now))


def _age(path: str, now: float) -> float:
    try:
        return now - os.path.getmtime(path)
    except OSError:
        return float("inf")


def nmcli(*args: str) -> str:
    try:
        return subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def networking(enabled: bool) -> None:
    nmcli("networking", "on" if enabled else "off")


def connected() -> bool:
    state = nmcli("-t", "-f", "STATE,CONNECTIVITY", "general")
    s, _, c = state.partition(":")
    return s.startswith("connected") and c in ("full", "unknown", "")


def installing() -> bool:
    """An install still running (going offline in the middle of one would break it)."""
    for name in INSTALLERS:
        if subprocess.run(["pgrep", "-x", name], capture_output=True).returncode == 0:
            return True
    return False


def notify(text: str, code: str | None = None) -> None:
    try:
        subprocess.run(["notify-send", "-i", "network-offline-symbolic", words("title", code), text], timeout=10)
    except (OSError, subprocess.SubprocessError):
        print(text)


def keep(offline: bool) -> None:
    """The switch: on → switched on, networking off; off → switched off, networking on."""
    if offline:
        os.makedirs(os.path.dirname(switch_path()), exist_ok=True)
        with open(switch_path(), "w", encoding="utf-8") as f:
            f.write("on\n")
        if not os.path.exists(updated_path()):  # the month for the reminder counts from the day it went offline
            _stamp(updated_path())
    else:
        try:
            os.remove(switch_path())
        except OSError:
            pass
    networking(not offline)
    notify(words("now_offline" if offline else "now_online"))


def go_online(wait=time.sleep, now=time.monotonic) -> bool:
    """Networking on, and wait (CONNECT_S at most) until a connection is up."""
    networking(True)
    deadline = now() + CONNECT_S
    while now() < deadline:
        if connected():
            return True
        wait(2)
    return False


def back_offline(wait=time.sleep) -> None:
    """After any install still running; only while offline mode is still on (switched off meanwhile, it stays)."""
    while installing():
        wait(5)
    if on():
        networking(False)
        _stamp(updated_path())
        notify(words("done"))


def updates() -> int:
    """Go online to install updates: the Updates window (D29), which goes online for the check and the install and
    back offline after them, once any install has finished."""
    from . import updates as window
    return window.main()


def remind(now: float | None = None) -> bool:
    """At most once a month, and only in offline mode: a month since the last updates (or since going offline)."""
    now = now or time.time()
    if not on() or _age(updated_path(), now) < MONTH_S or _age(reminded_path(), now) < MONTH_S:
        return False
    _stamp(reminded_path(), now)
    notify(words("remind"))
    return True


def main(argv: list[str]) -> int:
    what = argv[0] if argv else ""
    if what in ("on", "off"):
        keep(what == "on")
        return 0
    if what == "updates":
        return updates()
    if what == "remind":
        remind()
        return 0
    print(__doc__.split("\n\n")[3].strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
