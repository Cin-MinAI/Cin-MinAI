# SPDX-License-Identifier: GPL-3.0-or-later
"""The Updates window (PLAN D29, SPEC §3.7.1): updates you can watch, every step a real check.

The list is what apt itself would install now (`apt-get -s dist-upgrade`, so updates Ubuntu releases gradually, its
phased updates, wait as they would in Update Manager), each with a plain name from its own description and the
security ones marked. Install asks for the administrator password once and shows each step as the admin mechanism
runs it (cinminai-admin's InstallUpdates and its UpdateStep signal): the safety snapshot when Timeshift is set up, the
download, every file's fingerprint against the signed list, the install, the check afterwards. Checking for updates
needs no password (`apt-get update`, apt checking every source's signature). In offline mode (D28) the window goes
online for the check and the install and back offline after. Update Manager stays one click away for experts.

    cinminai-updates

Written by Claude (not a native speaker of es/pt/fr/de/ja): wants a native speaker's review (D36).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid

from . import offline

ADMIN = ("org.cinminai.Admin1", "/org/cinminai/Admin1", "org.cinminai.Admin1")
# `apt-get -s` lines (the admin mechanism reads the same lines: cin_minai/admin/updates.py INST_RE)
INST_RE = re.compile(r"^Inst (?P<name>\S+) (?:\[(?P<old>[^\]]+)\] )?\((?P<new>\S+) (?P<origins>.*?) ?\[(?P<arch>[^\]]+)\]\)")
REMV_RE = re.compile(r"^Remv (?P<name>\S+)")
STEPS = ("connect", "genuine", "snapshot", "download", "fingerprints", "install", "after", "back")
SOUNDS = {"start": "message", "tick": "audio-volume-change", "done": "complete", "warn": "dialog-warning"}

WORDS = {
    "en": {"title": "Updates", "checking": "Checking for updates…", "uptodate": "This computer is up to date.",
           "waiting": "{n} updates waiting", "waiting_sec": "{n} updates waiting ({s} security)",
           "security": "Security fix", "phased": "{n} more are being released gradually by Ubuntu. They'll come "
           "in the next few days.", "removes": "Some updates would remove a program ({names}), so they're left "
           "to Update Manager.", "offline": "This computer is offline. Go online to check for updates? It goes "
           "back offline afterwards.", "go_online": "Go online and check",
           "snapshot": "Take a safety snapshot first (Timeshift), so you can go back if anything goes wrong",
           "no_snapshot": "No safety snapshot: Timeshift isn't set up.", "set_up": "Set up Timeshift",
           "install": "Install {n} updates", "again": "Check again", "expert": "Update Manager (for experts)",
           "details": "Details", "close": "Close", "no_check": "Couldn't check for updates: {why}",
           "connect": "Going online", "connect_ok": "online for the updates",
           "genuine": "Checking the updates are genuine", "genuine_ok": "signed, checked by apt: {sources}",
           "snapshot_step": "Taking a safety snapshot (Timeshift)", "snapshot_ok": "you can go back if anything "
           "goes wrong", "snapshot_skip": "skipped: Timeshift isn't set up",
           "download": "Downloading {n} updates", "download_ok": "{n} files",
           "fingerprints": "Checking every file's fingerprint", "fingerprints_ok": "{good} of {files} match the "
           "signed list", "fingerprints_bad": "{bad} didn't match the signed list",
           "install_step": "Installing", "install_ok": "{n} updates installed",
           "after": "Checking the system afterwards", "after_ok": "everything is in order",
           "after_restart": "everything is in order. Restart the computer to finish",
           "after_bad": "something didn't finish: {what}", "back": "Going back offline", "back_ok": "offline again",
           "done": "Done: {n} updates installed.", "done_restart": "Done: {n} updates installed. Restart the "
           "computer when you're ready to finish.", "not_genuine": "These updates couldn't be proven genuine, so "
           "nothing was installed.", "failed": "Stopped: {why}", "cancelled": "Nothing was installed: the "
           "password wasn't given.", "no_connection": "Couldn't get online within a minute and a half. Check the "
           "cable or the Wi-Fi, then try again."},
    "es": {"title": "Actualizaciones", "checking": "Buscando actualizaciones…",
           "uptodate": "Este equipo está al día.", "waiting": "{n} actualizaciones pendientes",
           "waiting_sec": "{n} actualizaciones pendientes ({s} de seguridad)", "security": "Corrección de seguridad",
           "phased": "Ubuntu está publicando otras {n} poco a poco. Llegarán en los próximos días.",
           "removes": "Algunas actualizaciones quitarían un programa ({names}), así que se dejan al Gestor de "
           "actualizaciones.", "offline": "Este equipo está sin conexión. ¿Conectarse para buscar actualizaciones? "
           "Después vuelve a desconectarse.", "go_online": "Conectarse y buscar",
           "snapshot": "Hacer antes una instantánea de seguridad (Timeshift), para poder volver atrás si algo sale "
           "mal", "no_snapshot": "Sin instantánea de seguridad: Timeshift no está configurado.",
           "set_up": "Configurar Timeshift", "install": "Instalar {n} actualizaciones", "again": "Buscar de nuevo",
           "expert": "Gestor de actualizaciones (para expertos)", "details": "Detalles", "close": "Cerrar",
           "no_check": "No se pudieron buscar actualizaciones: {why}", "connect": "Conectándose",
           "connect_ok": "conectado para las actualizaciones",
           "genuine": "Comprobando que las actualizaciones son auténticas",
           "genuine_ok": "firmadas, comprobado por apt: {sources}",
           "snapshot_step": "Haciendo una instantánea de seguridad (Timeshift)",
           "snapshot_ok": "puedes volver atrás si algo sale mal",
           "snapshot_skip": "omitido: Timeshift no está configurado", "download": "Descargando {n} actualizaciones",
           "download_ok": "{n} archivos", "fingerprints": "Comprobando la huella de cada archivo",
           "fingerprints_ok": "{good} de {files} coinciden con la lista firmada",
           "fingerprints_bad": "{bad} no coincide con la lista firmada", "install_step": "Instalando",
           "install_ok": "{n} actualizaciones instaladas", "after": "Comprobando el sistema después",
           "after_ok": "todo está en orden",
           "after_restart": "todo está en orden. Reinicia el equipo para terminar",
           "after_bad": "algo no terminó: {what}", "back": "Volviendo a desconectarse", "back_ok": "sin conexión de "
           "nuevo", "done": "Listo: {n} actualizaciones instaladas.", "done_restart": "Listo: {n} actualizaciones "
           "instaladas. Reinicia el equipo cuando quieras para terminar.", "not_genuine": "No se pudo demostrar "
           "que estas actualizaciones son auténticas, así que no se instaló nada.", "failed": "Detenido: {why}",
           "cancelled": "No se instaló nada: no se dio la contraseña.", "no_connection": "No se pudo conectar en "
           "un minuto y medio. Revisa el cable o el wifi y vuelve a intentarlo."},
    "pt": {"title": "Atualizações", "checking": "Procurando atualizações…",
           "uptodate": "Este computador está atualizado.", "waiting": "{n} atualizações pendentes",
           "waiting_sec": "{n} atualizações pendentes ({s} de segurança)", "security": "Correção de segurança",
           "phased": "O Ubuntu está liberando mais {n} aos poucos. Elas chegam nos próximos dias.",
           "removes": "Algumas atualizações removeriam um programa ({names}), então ficam para o Gerenciador de "
           "atualizações.", "offline": "Este computador está offline. Conectar para procurar atualizações? Depois "
           "ele volta a ficar offline.", "go_online": "Conectar e procurar",
           "snapshot": "Tirar antes um instantâneo de segurança (Timeshift), para poder voltar atrás se algo der "
           "errado", "no_snapshot": "Sem instantâneo de segurança: o Timeshift não está configurado.",
           "set_up": "Configurar o Timeshift", "install": "Instalar {n} atualizações", "again": "Procurar de novo",
           "expert": "Gerenciador de atualizações (para especialistas)", "details": "Detalhes", "close": "Fechar",
           "no_check": "Não foi possível procurar atualizações: {why}", "connect": "Conectando",
           "connect_ok": "conectado para as atualizações", "genuine": "Verificando se as atualizações são autênticas",
           "genuine_ok": "assinadas, verificado pelo apt: {sources}",
           "snapshot_step": "Tirando um instantâneo de segurança (Timeshift)",
           "snapshot_ok": "dá para voltar atrás se algo der errado",
           "snapshot_skip": "pulado: o Timeshift não está configurado", "download": "Baixando {n} atualizações",
           "download_ok": "{n} arquivos", "fingerprints": "Verificando a impressão digital de cada arquivo",
           "fingerprints_ok": "{good} de {files} conferem com a lista assinada",
           "fingerprints_bad": "{bad} não confere com a lista assinada", "install_step": "Instalando",
           "install_ok": "{n} atualizações instaladas", "after": "Verificando o sistema depois",
           "after_ok": "está tudo em ordem",
           "after_restart": "está tudo em ordem. Reinicie o computador para terminar",
           "after_bad": "algo não terminou: {what}", "back": "Voltando a ficar offline", "back_ok": "offline de "
           "novo", "done": "Pronto: {n} atualizações instaladas.", "done_restart": "Pronto: {n} atualizações "
           "instaladas. Reinicie o computador quando quiser para terminar.", "not_genuine": "Não foi possível "
           "provar que estas atualizações são autênticas, então nada foi instalado.", "failed": "Parado: {why}",
           "cancelled": "Nada foi instalado: a senha não foi informada.", "no_connection": "Não foi possível "
           "conectar em um minuto e meio. Verifique o cabo ou o Wi-Fi e tente de novo."},
    "fr": {"title": "Mises à jour", "checking": "Recherche des mises à jour…",
           "uptodate": "Cet ordinateur est à jour.", "waiting": "{n} mises à jour en attente",
           "waiting_sec": "{n} mises à jour en attente ({s} de sécurité)", "security": "Correctif de sécurité",
           "phased": "Ubuntu publie {n} autres mises à jour progressivement. Elles arriveront dans les prochains "
           "jours.", "removes": "Certaines mises à jour supprimeraient un programme ({names}) : elles sont laissées "
           "au Gestionnaire de mises à jour.", "offline": "Cet ordinateur est hors ligne. Se connecter pour "
           "chercher les mises à jour ? Il repasse hors ligne ensuite.", "go_online": "Se connecter et chercher",
           "snapshot": "Prendre d'abord un instantané de sécurité (Timeshift), pour pouvoir revenir en arrière si "
           "quelque chose se passe mal", "no_snapshot": "Pas d'instantané de sécurité : Timeshift n'est pas "
           "configuré.", "set_up": "Configurer Timeshift", "install": "Installer {n} mises à jour",
           "again": "Chercher à nouveau", "expert": "Gestionnaire de mises à jour (pour les experts)",
           "details": "Détails", "close": "Fermer", "no_check": "Impossible de chercher les mises à jour : {why}",
           "connect": "Connexion", "connect_ok": "en ligne pour les mises à jour",
           "genuine": "Vérification de l'authenticité des mises à jour",
           "genuine_ok": "signées, vérifié par apt : {sources}",
           "snapshot_step": "Instantané de sécurité (Timeshift)",
           "snapshot_ok": "vous pouvez revenir en arrière si quelque chose se passe mal",
           "snapshot_skip": "ignoré : Timeshift n'est pas configuré", "download": "Téléchargement de {n} mises à "
           "jour", "download_ok": "{n} fichiers", "fingerprints": "Vérification de l'empreinte de chaque fichier",
           "fingerprints_ok": "{good} sur {files} correspondent à la liste signée",
           "fingerprints_bad": "{bad} ne correspond pas à la liste signée", "install_step": "Installation",
           "install_ok": "{n} mises à jour installées", "after": "Vérification du système après coup",
           "after_ok": "tout est en ordre",
           "after_restart": "tout est en ordre. Redémarrez l'ordinateur pour terminer",
           "after_bad": "quelque chose n'a pas abouti : {what}", "back": "Retour hors ligne",
           "back_ok": "de nouveau hors ligne", "done": "Terminé : {n} mises à jour installées.",
           "done_restart": "Terminé : {n} mises à jour installées. Redémarrez l'ordinateur quand vous voulez pour "
           "terminer.", "not_genuine": "L'authenticité de ces mises à jour n'a pas pu être prouvée : rien n'a été "
           "installé.", "failed": "Arrêté : {why}", "cancelled": "Rien n'a été installé : le mot de passe n'a pas "
           "été donné.", "no_connection": "Impossible de se connecter en une minute et demie. Vérifiez le câble ou "
           "le Wi-Fi, puis réessayez."},
    "de": {"title": "Updates", "checking": "Suche nach Updates…", "uptodate": "Dieser Computer ist auf dem neuesten "
           "Stand.", "waiting": "{n} Updates warten", "waiting_sec": "{n} Updates warten ({s} für die Sicherheit)",
           "security": "Sicherheitskorrektur", "phased": "{n} weitere gibt Ubuntu nach und nach frei. Sie kommen in "
           "den nächsten Tagen.", "removes": "Einige Updates würden ein Programm entfernen ({names}), daher bleiben "
           "sie der Aktualisierungsverwaltung überlassen.", "offline": "Dieser Computer ist offline. Online gehen, "
           "um nach Updates zu suchen? Danach geht er wieder offline.", "go_online": "Online gehen und suchen",
           "snapshot": "Vorher eine Sicherheitskopie anlegen (Timeshift), damit Sie zurück können, falls etwas "
           "schiefgeht", "no_snapshot": "Keine Sicherheitskopie: Timeshift ist nicht eingerichtet.",
           "set_up": "Timeshift einrichten", "install": "{n} Updates installieren", "again": "Erneut suchen",
           "expert": "Aktualisierungsverwaltung (für Fachleute)", "details": "Details", "close": "Schließen",
           "no_check": "Konnte nicht nach Updates suchen: {why}", "connect": "Online gehen",
           "connect_ok": "online für die Updates", "genuine": "Prüfen, ob die Updates echt sind",
           "genuine_ok": "signiert, von apt geprüft: {sources}",
           "snapshot_step": "Sicherheitskopie anlegen (Timeshift)",
           "snapshot_ok": "Sie können zurück, falls etwas schiefgeht",
           "snapshot_skip": "übersprungen: Timeshift ist nicht eingerichtet", "download": "{n} Updates herunterladen",
           "download_ok": "{n} Dateien", "fingerprints": "Fingerabdruck jeder Datei prüfen",
           "fingerprints_ok": "{good} von {files} stimmen mit der signierten Liste überein",
           "fingerprints_bad": "{bad} stimmt nicht mit der signierten Liste überein", "install_step": "Installieren",
           "install_ok": "{n} Updates installiert", "after": "Das System danach prüfen",
           "after_ok": "alles in Ordnung",
           "after_restart": "alles in Ordnung. Starten Sie den Computer neu, um abzuschließen",
           "after_bad": "etwas wurde nicht fertig: {what}", "back": "Wieder offline gehen",
           "back_ok": "wieder offline", "done": "Fertig: {n} Updates installiert.", "done_restart": "Fertig: {n} "
           "Updates installiert. Starten Sie den Computer neu, wenn es Ihnen passt, um abzuschließen.",
           "not_genuine": "Es ließ sich nicht nachweisen, dass diese Updates echt sind, daher wurde nichts "
           "installiert.", "failed": "Angehalten: {why}", "cancelled": "Nichts wurde installiert: Das Passwort wurde "
           "nicht eingegeben.", "no_connection": "Innerhalb von anderthalb Minuten keine Verbindung. Prüfen Sie das "
           "Kabel oder das WLAN und versuchen Sie es erneut."},
    "ja": {"title": "アップデート", "checking": "アップデートを確認しています…",
           "uptodate": "このコンピューターは最新の状態です。", "waiting": "{n}件のアップデートがあります",
           "waiting_sec": "{n}件のアップデートがあります（うちセキュリティ{s}件）", "security": "セキュリティ修正",
           "phased": "ほかに{n}件をUbuntuが段階的に公開しています。数日のうちに届きます。",
           "removes": "一部のアップデートはプログラム（{names}）を削除するため、アップデートマネージャーに任せます。",
           "offline": "このコンピューターはオフラインです。オンラインにしてアップデートを確認しますか？終わったらオフラインに戻ります。",
           "go_online": "オンラインにして確認", "snapshot": "先に安全のためのスナップショットを作成する（Timeshift）。"
           "問題が起きても元に戻せます", "no_snapshot": "安全のためのスナップショットなし：Timeshiftが設定されていません。",
           "set_up": "Timeshiftを設定", "install": "{n}件のアップデートをインストール", "again": "もう一度確認",
           "expert": "アップデートマネージャー（上級者向け）", "details": "詳細", "close": "閉じる",
           "no_check": "アップデートを確認できませんでした：{why}", "connect": "オンラインにしています",
           "connect_ok": "アップデートのためにオンライン", "genuine": "アップデートが本物か確認しています",
           "genuine_ok": "署名済み、aptが確認：{sources}", "snapshot_step": "安全のためのスナップショットを作成（Timeshift）",
           "snapshot_ok": "問題が起きても元に戻せます", "snapshot_skip": "省略：Timeshiftが設定されていません",
           "download": "{n}件のアップデートをダウンロード", "download_ok": "{n}個のファイル",
           "fingerprints": "各ファイルの指紋を確認", "fingerprints_ok": "{files}個中{good}個が署名済みの一覧と一致",
           "fingerprints_bad": "{bad}が署名済みの一覧と一致しません", "install_step": "インストール",
           "install_ok": "{n}件のアップデートをインストールしました", "after": "インストール後のシステムを確認",
           "after_ok": "すべて正常です", "after_restart": "すべて正常です。仕上げにコンピューターを再起動してください",
           "after_bad": "完了していないものがあります：{what}", "back": "オフラインに戻しています", "back_ok": "オフラインに戻りました",
           "done": "完了：{n}件のアップデートをインストールしました。",
           "done_restart": "完了：{n}件のアップデートをインストールしました。都合のよいときに再起動して仕上げてください。",
           "not_genuine": "これらのアップデートが本物だと確認できなかったため、何もインストールしていません。",
           "failed": "停止しました：{why}", "cancelled": "何もインストールしていません：パスワードが入力されませんでした。",
           "no_connection": "1分半以内にオンラインになれませんでした。ケーブルかWi-Fiを確認して、もう一度お試しください。"},
}


def words(key: str, code: str | None = None, **fill) -> str:
    text = WORDS.get(code or offline.lang(), WORDS["en"])[key]
    return text.format(**fill) if fill else text


def simulate() -> str:
    """apt's own plan for an upgrade now, without root (a simulation reads the lists only)."""
    env = dict(os.environ, LANG="C", LC_ALL="C", LANGUAGE="")
    return subprocess.run(["apt-get", "-s", "-o", "APT::Get::Show-User-Simulation-Note=false", "dist-upgrade"],
                          capture_output=True, text=True, timeout=120, env=env).stdout


def plan(output: str) -> dict:
    """What an upgrade would do: the updates (installed packages getting a new version), packages it would add
    (a new kernel), remove, and the updates Ubuntu holds back for now (phased)."""
    ups, new, gone, phased, in_phased = [], [], [], 0, False
    for line in output.splitlines():
        m = INST_RE.match(line)
        if m:
            item = {"name": m.group("name"), "old": m.group("old") or "", "version": m.group("new"),
                    "arch": m.group("arch"), "security": "-security" in m.group("origins")}
            (ups if item["old"] else new).append(item)
            in_phased = False
            continue
        r = REMV_RE.match(line)
        if r:
            gone.append(r.group("name"))
        if line.startswith("The following upgrades have been deferred due to phasing"):
            in_phased = True
        elif in_phased and line.startswith("  "):
            phased += len(line.split())
        else:
            in_phased = False
    return {"updates": ups, "new": new, "remove": gone, "phased": phased}


def plain_names(items: list[dict]) -> None:
    """Each update's one-line description (in the person's language where apt has the translation)."""
    try:
        import apt
        cache = apt.Cache()
    except Exception:
        return
    for item in items:
        try:
            item["plain"] = cache[item["name"]].candidate.summary or ""
        except Exception:
            item["plain"] = ""


def request(items: list[dict]) -> list[str]:
    """The exact versions for InstallUpdates (an architecture-qualified name stays as apt printed it)."""
    return [f"{i['name']}={i['version']}" for i in items]


def headline(p: dict, code: str | None = None) -> str:
    n, s = len(p["updates"]), sum(1 for i in p["updates"] if i["security"])
    if not n:
        return words("uptodate", code)
    return words("waiting_sec", code, n=n, s=s) if s else words("waiting", code, n=n)


def step_text(step: str, state: str, detail: dict, code: str | None = None) -> tuple[str, str]:
    """The line for a step: (what, how it went)."""
    title = {"snapshot": "snapshot_step", "install": "install_step"}.get(step, step)
    if step == "download":
        what = words("download", code, n=detail.get("count", detail.get("files", "")))
    else:
        what = words(title, code)
    if state == "ok":
        how = {"connect": lambda: words("connect_ok", code),
               "genuine": lambda: words("genuine_ok", code, sources=", ".join(detail.get("sources", [])) or "apt"),
               "snapshot": lambda: words("snapshot_ok", code),
               "download": lambda: words("download_ok", code, n=detail.get("files", 0)),
               "fingerprints": lambda: words("fingerprints_ok", code, good=detail.get("good", 0),
                                             files=detail.get("files", 0)),
               "install": lambda: words("install_ok", code, n=detail.get("count", 0)),
               "after": lambda: words("after_restart" if detail.get("restart") else "after_ok", code),
               "back": lambda: words("back_ok", code)}[step]()
    elif state == "skipped":
        how = words("snapshot_skip", code) if step == "snapshot" else ""
    elif state == "failed":
        if step == "fingerprints":
            how = words("fingerprints_bad", code, bad=", ".join(detail.get("bad", [])[:3]))
        elif step == "after":
            how = words("after_bad", code, what=", ".join(detail.get("failed", [])) or detail.get("broken", "")[:80])
        else:
            how = detail.get("error", "")[-160:]
    else:
        how = ""
    return what, how


def not_genuine(message: str) -> bool:
    """The mechanism stopped because apt couldn't check a source's signature (its error carries the lines)."""
    try:
        return bool(json.loads(message.split("Error.Failed:", 1)[-1].strip()).get("signature"))
    except (ValueError, AttributeError):
        return False


def failure(message: str, code: str | None = None) -> str:
    """What the person reads when the mechanism refused or stopped."""
    if "Error.Dismissed" in message or "Error.NotAuthorized" in message:
        return words("cancelled", code)
    if not_genuine(message):
        return words("not_genuine", code)
    return words("failed", code, why=message.split(": ", 1)[-1][-200:])


def timeshift_ready() -> bool:
    try:
        with open("/etc/timeshift/timeshift.json", encoding="utf-8") as f:
            return bool(json.load(f).get("backup_device_uuid"))
    except (OSError, ValueError):
        return False


def sound(kind: str) -> None:
    """The shared sounds (SPEC §5.7): a calm start, a soft tick per verified step, a chime, a warning. Every sound
    has its line on screen too."""
    if shutil.which("canberra-gtk-play"):
        try:
            subprocess.Popen(["canberra-gtk-play", "-i", SOUNDS[kind]], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            pass


def window() -> int:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gio, GLib, Gtk

    code = offline.lang()
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    state = {"plan": None, "online": False, "job": "", "sources": [], "rows": [], "busy": False}

    win = Gtk.Window(title=words("title", code))
    win.set_default_size(620, 640)
    win.set_border_width(16)
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    win.add(outer)
    head = Gtk.Label(xalign=0, wrap=True)
    head.get_style_context().add_class("title")
    note = Gtk.Label(xalign=0, wrap=True, max_width_chars=70)
    outer.pack_start(head, False, False, 0)
    outer.pack_start(note, False, False, 0)
    scroll = Gtk.ScrolledWindow(vexpand=True)
    listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    scroll.add(listing)
    outer.pack_start(scroll, True, True, 0)
    snap = Gtk.CheckButton(label=words("snapshot", code))
    snap_none = Gtk.Box(spacing=8)
    snap_none.pack_start(Gtk.Label(label=words("no_snapshot", code), xalign=0, wrap=True), False, False, 0)
    set_up = Gtk.LinkButton.new_with_label("", words("set_up", code))
    set_up.connect("activate-link", lambda b: (subprocess.Popen(["timeshift-launcher"], start_new_session=True)
                                               if shutil.which("timeshift-launcher") else None) or True)
    snap_none.pack_start(set_up, False, False, 0)
    outer.pack_start(snap, False, False, 0)
    outer.pack_start(snap_none, False, False, 0)
    details = Gtk.Expander(label=words("details", code))
    log = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
    log_scroll = Gtk.ScrolledWindow(min_content_height=120)
    log_scroll.add(log)
    details.add(log_scroll)
    outer.pack_start(details, False, False, 0)
    buttons = Gtk.Box(spacing=8)
    expert = Gtk.Button(label=words("expert", code))
    expert.set_relief(Gtk.ReliefStyle.NONE)
    again = Gtk.Button(label=words("again", code))
    install = Gtk.Button()
    install.get_style_context().add_class("suggested-action")
    buttons.pack_start(expert, False, False, 0)
    buttons.pack_end(install, False, False, 0)
    buttons.pack_end(again, False, False, 0)
    outer.pack_start(buttons, False, False, 0)

    def say_log(text: str) -> None:
        buf = log.get_buffer()
        buf.insert(buf.get_end_iter(), text.rstrip() + "\n")

    def clear() -> None:
        for child in listing.get_children():
            listing.remove(child)
        state["rows"] = []

    def busy(on: bool) -> None:
        state["busy"] = on
        again.set_sensitive(not on)
        install.set_sensitive(not on and bool(state["plan"] and state["plan"]["updates"]))
        snap.set_sensitive(not on)

    def show_plan(p: dict) -> None:
        state["plan"] = p
        clear()
        again.set_label(words("again", code))
        head.set_markup(f"<big><b>{GLib.markup_escape_text(headline(p, code))}</b></big>")
        notes = []
        if p["phased"]:
            notes.append(words("phased", code, n=p["phased"]))
        if p["remove"]:
            notes.append(words("removes", code, names=", ".join(p["remove"][:5])))
        note.set_text("\n".join(notes))
        for item in sorted(p["updates"], key=lambda i: (not i["security"], i["name"])):
            row = Gtk.Box(spacing=10)
            tick = Gtk.CheckButton(active=True)
            tick.connect("toggled", lambda b: count())
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            plain = item.get("plain") or item["name"]
            if item["security"]:
                plain = f"{words('security', code)}: {plain}"
            top = Gtk.Label(xalign=0, wrap=True)
            top.set_markup(f"<b>{GLib.markup_escape_text(plain)}</b>")
            small = Gtk.Label(xalign=0)
            small.set_markup(f"<small>{GLib.markup_escape_text(item['name'])}  {GLib.markup_escape_text(item['old'])}"
                             f" → {GLib.markup_escape_text(item['version'])}</small>")
            small.get_style_context().add_class("dim-label")
            text.pack_start(top, False, False, 0)
            text.pack_start(small, False, False, 0)
            row.pack_start(tick, False, False, 0)
            row.pack_start(text, True, True, 0)
            listing.add(row)
            state["rows"].append((tick, item))
        ready = timeshift_ready()
        snap.set_visible(ready)
        snap.set_active(ready)
        snap_none.set_visible(not ready and bool(p["updates"]))
        listing.show_all()
        count()
        busy(False)

    def chosen() -> list[dict]:
        return [item for tick, item in state["rows"] if tick.get_active()]

    def count() -> None:
        n = len(chosen())
        install.set_label(words("install", code, n=n))
        install.set_visible(bool(state["plan"] and state["plan"]["updates"]))
        install.set_sensitive(n > 0 and not state["busy"])

    def step_row(step: str) -> tuple:
        row = Gtk.Box(spacing=10)
        mark = Gtk.Spinner()
        icon = Gtk.Image()
        what = Gtk.Label(xalign=0)
        how = Gtk.Label(xalign=0, wrap=True)
        how.get_style_context().add_class("dim-label")
        row.pack_start(mark, False, False, 0)
        row.pack_start(icon, False, False, 0)
        row.pack_start(what, False, False, 0)
        row.pack_start(how, True, True, 0)
        listing.add(row)
        row.show_all()
        icon.hide()
        return mark, icon, what, how

    steps: dict = {}

    def show_step(step: str, st: str, detail: dict) -> None:
        if step not in steps:
            steps[step] = step_row(step)
        mark, icon, what, how = steps[step]
        w, h = step_text(step, st, detail, code)
        what.set_text(w)
        how.set_text(h)
        if st == "running":
            mark.show()
            mark.start()
            return
        mark.stop()
        mark.hide()
        icon.set_from_icon_name({"ok": "emblem-ok-symbolic", "skipped": "action-unavailable-symbolic"}.get(
            st, "dialog-error-symbolic"), Gtk.IconSize.BUTTON)
        icon.show()
        say_log(f"{step}: {st} {json.dumps(detail, ensure_ascii=False)}")
        sound("tick" if st == "ok" else "warn" if st == "failed" else "tick")

    def admin(method: str, args, signature: str | None, done, interactive: bool = False) -> None:
        flags = Gio.DBusCallFlags.ALLOW_INTERACTIVE_AUTHORIZATION if interactive else Gio.DBusCallFlags.NONE

        def reply(conn, result) -> None:
            try:
                out = conn.call_finish(result).unpack()
                done(json.loads(out[0]) if out and out[0] else {}, "")
            except GLib.Error as e:
                done(None, f"{Gio.DBusError.get_remote_error(e) or ''}: {e.message}")
        bus.call(*ADMIN, method, GLib.Variant(signature, args) if signature else None, GLib.VariantType("(s)"),
                 flags, -1, None, reply)

    def go_online_then(then) -> None:
        """In offline mode: online first (in the background, the window stays responsive)."""
        if not offline.on() or state["online"]:
            then()
            return
        show_step("connect", "running", {})

        def wait() -> None:
            ok = offline.go_online()
            GLib.idle_add(after, ok)

        def after(ok: bool) -> bool:
            if not ok:
                show_step("connect", "failed", {"error": words("no_connection", code)})
                offline.networking(False)
                head.set_text(words("no_connection", code))
                busy(False)
                return False
            state["online"] = True
            show_step("connect", "ok", {})
            then()
            return False
        import threading
        threading.Thread(target=wait, daemon=True).start()

    def back_offline(installed: bool = False) -> None:
        """Offline again; after an install, offline mode's own step (it stamps when updates were last installed,
        for its monthly reminder)."""
        if state["online"] and offline.on():
            offline.back_offline() if installed else offline.networking(False)
            state["online"] = False

    def check(*_) -> None:
        busy(True)
        clear()
        steps.clear()
        head.set_markup(f"<big><b>{GLib.markup_escape_text(words('checking', code))}</b></big>")
        note.set_text("")
        install.set_visible(False)

        def refreshed(out, error) -> None:
            if error:
                say_log(error)
                head.set_text(failure(error, code) if not_genuine(error) else words("no_check", code, why=error[-200:]))
                if not_genuine(error):
                    sound("warn")
                busy(False)
                return
            state["sources"] = (out or {}).get("sources", [])
            say_log("apt-get update: " + ", ".join(state["sources"]))
            p = plan(simulate())
            plain_names(p["updates"])
            show_plan(p)
            if offline.on() and not p["updates"]:
                back_offline()
        go_online_then(lambda: admin("RefreshUpdates", None, None, refreshed))

    def run_install(*_) -> None:
        items = chosen()
        if not items:
            return
        busy(True)
        clear()
        steps.clear()
        state["job"] = uuid.uuid4().hex[:16]
        head.set_markup(f"<big><b>{GLib.markup_escape_text(words('install', code, n=len(items)))}</b></big>")
        note.set_text("")
        snap.set_visible(False)
        snap_none.set_visible(False)
        sound("start")
        if state["online"]:
            show_step("connect", "ok", {})
        show_step("genuine", "ok", {"sources": state["sources"]})

        def finished(out, error) -> None:
            state["busy"], state["job"] = False, ""
            install.set_visible(False)
            if offline.on() and state["online"]:
                show_step("back", "running", {})
                back_offline(installed=not error)
                show_step("back", "ok", {})
            if error:
                say_log(error)
                head.set_text(failure(error, code))
                sound("warn")
                again.set_sensitive(True)
                return
            n = (out or {}).get("installed", 0)
            head.set_markup("<big><b>" + GLib.markup_escape_text(
                words("done_restart" if (out or {}).get("restart") else "done", code, n=n)) + "</b></big>")
            sound("done")
            again.set_sensitive(True)
        admin("InstallUpdates", (request(items), snap.get_active() and timeshift_ready(), state["job"]),
              "(asbs)", finished, interactive=True)

    def on_step(_conn, _sender, _path, _iface, _signal, params) -> None:
        job, step, st, detail = params.unpack()
        if job == state["job"]:
            try:
                show_step(step, st, json.loads(detail or "{}"))
            except ValueError:
                show_step(step, st, {})

    bus.signal_subscribe(ADMIN[0], ADMIN[2], "UpdateStep", ADMIN[1], None, Gio.DBusSignalFlags.NONE, on_step)

    def open_expert(*_) -> None:
        for cmd in (["mintupdate"], ["update-manager"]):
            if shutil.which(cmd[0]):
                subprocess.Popen(cmd, start_new_session=True)
                return

    def leave(*_) -> bool:
        if state["busy"] and state["job"]:
            return True  # never close in the middle of an install
        back_offline()
        Gtk.main_quit()
        return False

    expert.connect("clicked", open_expert)
    again.connect("clicked", check)
    install.connect("clicked", run_install)
    win.connect("delete-event", leave)
    win.show_all()
    snap.hide()
    snap_none.hide()
    install.hide()
    if offline.on():
        head.set_markup(f"<big><b>{GLib.markup_escape_text(words('title', code))}</b></big>")
        note.set_text(words("offline", code))
        again.set_label(words("go_online", code))
    else:
        check()
    Gtk.main()
    return 0


def main(argv: list[str] | None = None) -> int:
    return window()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
