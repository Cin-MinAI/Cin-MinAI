# SPDX-License-Identifier: GPL-3.0-or-later
"""The Updates window (PLAN D29, SPEC §3.7.1): updates you can watch, every step a real check.

The list is what apt itself would install now (`apt-get -s dist-upgrade`, so updates Ubuntu releases gradually, its
phased updates, wait as they would in Update Manager), each with a plain name from its own description and the
security ones marked. Install asks for the administrator password once and shows each step as the admin mechanism
runs it (cinminai-admin's InstallUpdates and its UpdateStep signal): the safety snapshot when Timeshift is set up, the
download, every file's fingerprint against the signed list, the install, the check afterwards. Checking for updates
needs no password (`apt-get update`, apt checking every source's signature). In offline mode (D28) the window goes
online for the check and the install and back offline after. Update Manager stays one click away for experts.

Holds (D89, slice 2; Ian: optional, unchecked, customizable): new updates can wait a number of days (off by default),
updates can install by themselves once a day (the daily timer, admin/auto.py), and the person can hold one update or
every update to a program until they release it. The admin mechanism's check marks what's held (the same rule the
timer uses); held updates come unticked, and ticking one installs it anyway: the person's call. A held security fix
that CISA lists as exploited now is said. Changing the settings asks for the password once. While the wait is on, a
security fix confirmed for its program by Debian's security team (OSV.dev) doesn't wait, and goes first when it fixes
something on CISA's list (slice 3, the emergency path); one that can't be confirmed waits like the rest and says so.

    cinminai-updates               the window
    cinminai-updates --notices     what the daily run needs the person to know, once each (the panel icon runs it)

Written by Claude (not a native speaker of es/pt/fr/de/ja): wants a native speaker's review (D36).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid

from . import offline

ADMIN = ("org.cinminai.Admin1", "/org/cinminai/Admin1", "org.cinminai.Admin1")
SETTINGS = "/etc/cinminai/updates.json"  # written by the admin mechanism (SetUpdateSettings), readable by all
STATUS = "/var/lib/cinminai/updates-status.json"  # the daily run's last result (admin/auto.py)
DAY = 86400
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


# the holds and automatic updates (D89, slice 2)
WORDS_HOLDS = {
    "en": {"wait_check": "Let new updates wait", "wait_days": "days first, so others have time to find a problem in "
           "them", "auto": "Install updates by themselves once a day (the ones nothing holds)",
           "save": "Save these settings", "saved": "Saved.", "unsaved": "Not saved yet: it asks for the password once.",
           "held_waiting": "Waiting until {when}", "held_update": "Held by you (this update)",
           "held_program": "Held by you (every update to this program)", "hold_menu": "Hold",
           "hold_update": "Hold this update", "hold_program": "Hold every update to this program",
           "release": "Stop holding it", "held_note": "{n} held: they're unticked. Tick one to install it anyway.",
           "kev": "CISA lists {cves} as being exploited now. It stays held: your call.",
           "kev_unknown": "Couldn't read CISA's list of exploited weaknesses just now.",
           "last_auto": "Last daily check: {when}. {n} installed, {held} held.",
           "last_auto_err": "Last daily check: {when}. It stopped: {why}.", "why_check": "it couldn't check",
           "why_battery": "it waits for the power cable", "why_install": "an install stopped",
           "why_after": "something didn't finish",
           "n_genuine": "An update source couldn't be proven genuine, so nothing was installed. Open Updates to see "
           "which.", "n_stopped": "The daily update stopped. Open Updates to see why.",
           "n_restart": "Updates were installed. Restart the computer when you're ready to finish.",
           "n_kev": "A security update you're holding fixes {cves}, which CISA lists as being exploited now. Open "
           "Updates to decide."},
    "es": {"wait_check": "Dejar esperar las actualizaciones nuevas", "wait_days": "días antes, para que otros tengan "
           "tiempo de encontrar un problema en ellas", "auto": "Instalar las actualizaciones solas una vez al día "
           "(las que nada retiene)", "save": "Guardar estos ajustes", "saved": "Guardado.",
           "unsaved": "Aún sin guardar: pide la contraseña una vez.", "held_waiting": "Esperando hasta {when}",
           "held_update": "Retenida por ti (esta actualización)",
           "held_program": "Retenida por ti (todas las actualizaciones de este programa)", "hold_menu": "Retener",
           "hold_update": "Retener esta actualización", "hold_program": "Retener todas las actualizaciones de este "
           "programa", "release": "Dejar de retenerla", "held_note": "{n} retenidas: están sin marcar. Marca una para "
           "instalarla de todos modos.", "kev": "La CISA indica que {cves} se está explotando ahora. Sigue retenida: "
           "tú decides.", "kev_unknown": "No se pudo leer ahora la lista de la CISA de vulnerabilidades explotadas.",
           "last_auto": "Última comprobación diaria: {when}. {n} instaladas, {held} retenidas.",
           "last_auto_err": "Última comprobación diaria: {when}. Se detuvo: {why}.",
           "why_check": "no pudo comprobar", "why_battery": "espera al cable de corriente",
           "why_install": "una instalación se detuvo", "why_after": "algo no terminó",
           "n_genuine": "No se pudo demostrar que una fuente de actualizaciones es auténtica, así que no se instaló "
           "nada. Abre Actualizaciones para ver cuál.", "n_stopped": "La actualización diaria se detuvo. Abre "
           "Actualizaciones para ver por qué.", "n_restart": "Se instalaron actualizaciones. Reinicia el equipo "
           "cuando quieras para terminar.", "n_kev": "Una actualización de seguridad que retienes corrige {cves}, que "
           "la CISA indica que se está explotando ahora. Abre Actualizaciones para decidir."},
    "pt": {"wait_check": "Deixar as atualizações novas esperarem", "wait_days": "dias antes, para outros terem tempo "
           "de achar um problema nelas", "auto": "Instalar as atualizações sozinhas uma vez por dia (as que nada "
           "segura)", "save": "Salvar estas configurações", "saved": "Salvo.",
           "unsaved": "Ainda não salvo: pede a senha uma vez.", "held_waiting": "Esperando até {when}",
           "held_update": "Segurada por você (esta atualização)",
           "held_program": "Segurada por você (todas as atualizações deste programa)", "hold_menu": "Segurar",
           "hold_update": "Segurar esta atualização", "hold_program": "Segurar todas as atualizações deste programa",
           "release": "Parar de segurar", "held_note": "{n} seguradas: estão desmarcadas. Marque uma para instalá-la "
           "mesmo assim.", "kev": "A CISA aponta {cves} como explorada agora. Continua segurada: você decide.",
           "kev_unknown": "Não foi possível ler agora a lista da CISA de vulnerabilidades exploradas.",
           "last_auto": "Última verificação diária: {when}. {n} instaladas, {held} seguradas.",
           "last_auto_err": "Última verificação diária: {when}. Parou: {why}.",
           "why_check": "não conseguiu verificar", "why_battery": "espera o cabo de energia",
           "why_install": "uma instalação parou", "why_after": "algo não terminou",
           "n_genuine": "Não foi possível provar que uma fonte de atualizações é autêntica, então nada foi instalado. "
           "Abra Atualizações para ver qual.", "n_stopped": "A atualização diária parou. Abra Atualizações para ver "
           "por quê.", "n_restart": "Atualizações foram instaladas. Reinicie o computador quando quiser para "
           "terminar.", "n_kev": "Uma atualização de segurança que você está segurando corrige {cves}, que a CISA "
           "aponta como explorada agora. Abra Atualizações para decidir."},
    "fr": {"wait_check": "Faire attendre les nouvelles mises à jour", "wait_days": "jours d'abord, pour laisser aux "
           "autres le temps d'y trouver un problème", "auto": "Installer les mises à jour toutes seules une fois par "
           "jour (celles que rien ne retient)", "save": "Enregistrer ces réglages", "saved": "Enregistré.",
           "unsaved": "Pas encore enregistré : le mot de passe est demandé une fois.",
           "held_waiting": "En attente jusqu'au {when}", "held_update": "Retenue par vous (cette mise à jour)",
           "held_program": "Retenue par vous (toutes les mises à jour de ce programme)", "hold_menu": "Retenir",
           "hold_update": "Retenir cette mise à jour", "hold_program": "Retenir toutes les mises à jour de ce "
           "programme", "release": "Ne plus la retenir", "held_note": "{n} retenues : elles sont décochées. Cochez-en "
           "une pour l'installer quand même.", "kev": "La CISA signale {cves} comme exploitée en ce moment. Elle reste "
           "retenue : à vous de décider.", "kev_unknown": "Impossible de lire pour l'instant la liste de la CISA des "
           "failles exploitées.", "last_auto": "Dernière vérification quotidienne : {when}. {n} installées, {held} "
           "retenues.", "last_auto_err": "Dernière vérification quotidienne : {when}. Elle s'est arrêtée : {why}.",
           "why_check": "impossible de vérifier", "why_battery": "elle attend le câble d'alimentation",
           "why_install": "une installation s'est arrêtée", "why_after": "quelque chose n'a pas abouti",
           "n_genuine": "L'authenticité d'une source de mises à jour n'a pas pu être prouvée : rien n'a été installé. "
           "Ouvrez Mises à jour pour voir laquelle.", "n_stopped": "La mise à jour quotidienne s'est arrêtée. Ouvrez "
           "Mises à jour pour voir pourquoi.", "n_restart": "Des mises à jour ont été installées. Redémarrez "
           "l'ordinateur quand vous voulez pour terminer.", "n_kev": "Une mise à jour de sécurité que vous retenez "
           "corrige {cves}, que la CISA signale comme exploitée en ce moment. Ouvrez Mises à jour pour décider."},
    "de": {"wait_check": "Neue Updates warten lassen", "wait_days": "Tage, damit andere Zeit haben, ein Problem darin "
           "zu finden", "auto": "Updates einmal am Tag selbst installieren (die, die nichts zurückhält)",
           "save": "Diese Einstellungen speichern", "saved": "Gespeichert.",
           "unsaved": "Noch nicht gespeichert: Das Passwort wird einmal abgefragt.",
           "held_waiting": "Wartet bis {when}", "held_update": "Von Ihnen zurückgehalten (dieses Update)",
           "held_program": "Von Ihnen zurückgehalten (alle Updates dieses Programms)", "hold_menu": "Zurückhalten",
           "hold_update": "Dieses Update zurückhalten", "hold_program": "Alle Updates dieses Programms zurückhalten",
           "release": "Nicht mehr zurückhalten", "held_note": "{n} zurückgehalten: Sie sind nicht angehakt. Haken Sie "
           "eines an, um es trotzdem zu installieren.", "kev": "Die CISA führt {cves} als derzeit ausgenutzt. Es "
           "bleibt zurückgehalten: Sie entscheiden.", "kev_unknown": "Die Liste der CISA mit ausgenutzten "
           "Schwachstellen ließ sich gerade nicht lesen.", "last_auto": "Letzte tägliche Prüfung: {when}. {n} "
           "installiert, {held} zurückgehalten.", "last_auto_err": "Letzte tägliche Prüfung: {when}. Sie hat "
           "angehalten: {why}.", "why_check": "sie konnte nicht prüfen", "why_battery": "sie wartet auf das Stromkabel",
           "why_install": "eine Installation hat angehalten", "why_after": "etwas wurde nicht fertig",
           "n_genuine": "Bei einer Update-Quelle ließ sich nicht nachweisen, dass sie echt ist, daher wurde nichts "
           "installiert. Öffnen Sie Updates, um zu sehen, welche.", "n_stopped": "Das tägliche Update hat "
           "angehalten. Öffnen Sie Updates, um zu sehen, warum.", "n_restart": "Updates wurden installiert. Starten "
           "Sie den Computer neu, wenn es Ihnen passt, um abzuschließen.", "n_kev": "Ein Sicherheitsupdate, das Sie "
           "zurückhalten, behebt {cves}, das die CISA als derzeit ausgenutzt führt. Öffnen Sie Updates, um zu "
           "entscheiden."},
    "ja": {"wait_check": "新しいアップデートを待たせる", "wait_days": "日間。その間にほかの人が問題を見つけられます",
           "auto": "1日に1回アップデートを自動でインストールする（保留されていないもの）", "save": "この設定を保存",
           "saved": "保存しました。", "unsaved": "まだ保存していません：パスワードを1回たずねます。",
           "held_waiting": "{when}まで待機中", "held_update": "あなたが保留中（このアップデート）",
           "held_program": "あなたが保留中（このプログラムのすべてのアップデート）", "hold_menu": "保留",
           "hold_update": "このアップデートを保留", "hold_program": "このプログラムのすべてのアップデートを保留",
           "release": "保留をやめる", "held_note": "{n}件を保留中：チェックが外れています。チェックを入れればそれでもインストールできます。",
           "kev": "CISAは{cves}を現在悪用されている脆弱性に挙げています。保留のままです。判断はあなたに任せます。",
           "kev_unknown": "CISAの悪用されている脆弱性の一覧を今は読めませんでした。",
           "last_auto": "前回の毎日の確認：{when}。{n}件インストール、{held}件保留。",
           "last_auto_err": "前回の毎日の確認：{when}。停止しました：{why}。", "why_check": "確認できませんでした",
           "why_battery": "電源ケーブルを待っています", "why_install": "インストールが止まりました",
           "why_after": "完了していないものがあります",
           "n_genuine": "アップデートの入手元が本物だと確認できなかったため、何もインストールしていません。どれかは「アップデート」を開いて確認してください。",
           "n_stopped": "毎日のアップデートが止まりました。理由は「アップデート」を開いて確認してください。",
           "n_restart": "アップデートをインストールしました。都合のよいときに再起動して仕上げてください。",
           "n_kev": "保留中のセキュリティアップデートは{cves}を修正します。CISAはこれを現在悪用されている脆弱性に挙げています。「アップデート」を開いて判断してください。"},
}
# the confirmations and the emergency path (D89, slice 3)
WORDS_EARLY = {
    "en": {"wait_note": "While they wait, security fixes are checked with Debian's security team (through OSV.dev) and "
           "CISA's list of weaknesses being exploited now; only the CVE numbers are sent. A fix they confirm doesn't "
           "wait.", "unconfirmed": "Couldn't be confirmed at an independent source, so it waits like the rest",
           "no_cve": "It names no CVE to confirm, so it waits like the rest",
           "early_confirmed": "Doesn't wait: Debian's security team confirms the fix ({cves})",
           "early_kev": "Goes first: it fixes {cves}, which CISA lists as exploited now, and Debian's security team "
           "confirms it",
           "n_early": "A fix for {cves}, which CISA lists as being exploited now, was installed early: Debian's security "
           "team confirmed it."},
    "es": {"wait_note": "Mientras esperan, las correcciones de seguridad se comprueban con el equipo de seguridad de "
           "Debian (a través de OSV.dev) y con la lista de la CISA de vulnerabilidades que se están explotando; solo se "
           "envían los números CVE. Una corrección que confirman no espera.",
           "unconfirmed": "No se pudo confirmar en una fuente independiente, así que espera como las demás",
           "no_cve": "No indica ningún CVE que confirmar, así que espera como las demás",
           "early_confirmed": "No espera: el equipo de seguridad de Debian confirma la corrección ({cves})",
           "early_kev": "Va primero: corrige {cves}, que la CISA indica que se está explotando, y el equipo de seguridad "
           "de Debian lo confirma",
           "n_early": "Una corrección de {cves}, que la CISA indica que se está explotando, se instaló antes: el equipo "
           "de seguridad de Debian la confirmó."},
    "pt": {"wait_note": "Enquanto esperam, as correções de segurança são verificadas com a equipe de segurança do "
           "Debian (pelo OSV.dev) e com a lista da CISA de vulnerabilidades sendo exploradas agora; só os números CVE "
           "são enviados. Uma correção que eles confirmam não espera.",
           "unconfirmed": "Não foi possível confirmar em uma fonte independente, então espera como as outras",
           "no_cve": "Não cita nenhum CVE para confirmar, então espera como as outras",
           "early_confirmed": "Não espera: a equipe de segurança do Debian confirma a correção ({cves})",
           "early_kev": "Vai primeiro: corrige {cves}, que a CISA aponta como explorada agora, e a equipe de segurança "
           "do Debian confirma",
           "n_early": "Uma correção para {cves}, que a CISA aponta como explorada agora, foi instalada antes: a equipe "
           "de segurança do Debian a confirmou."},
    "fr": {"wait_note": "Pendant l'attente, les correctifs de sécurité sont vérifiés auprès de l'équipe de sécurité de "
           "Debian (via OSV.dev) et de la liste de la CISA des failles exploitées en ce moment ; seuls les numéros CVE "
           "sont envoyés. Un correctif qu'ils confirment n'attend pas.",
           "unconfirmed": "Impossible de le confirmer auprès d'une source indépendante : il attend comme les autres",
           "no_cve": "Il ne cite aucun CVE à confirmer : il attend comme les autres",
           "early_confirmed": "N'attend pas : l'équipe de sécurité de Debian confirme le correctif ({cves})",
           "early_kev": "Passe en premier : il corrige {cves}, que la CISA signale comme exploitée en ce moment, et "
           "l'équipe de sécurité de Debian le confirme",
           "n_early": "Un correctif pour {cves}, que la CISA signale comme exploitée en ce moment, a été installé plus "
           "tôt : l'équipe de sécurité de Debian l'a confirmé."},
    "de": {"wait_note": "Während sie warten, werden Sicherheitskorrekturen beim Sicherheitsteam von Debian (über "
           "OSV.dev) und mit der CISA-Liste derzeit ausgenutzter Schwachstellen geprüft; nur die CVE-Nummern werden "
           "gesendet. Eine Korrektur, die sie bestätigen, wartet nicht.",
           "unconfirmed": "Ließ sich bei keiner unabhängigen Quelle bestätigen, daher wartet sie wie die anderen",
           "no_cve": "Sie nennt keine CVE zum Bestätigen, daher wartet sie wie die anderen",
           "early_confirmed": "Wartet nicht: Das Sicherheitsteam von Debian bestätigt die Korrektur ({cves})",
           "early_kev": "Kommt zuerst: Sie behebt {cves}, das die CISA als derzeit ausgenutzt führt, und das "
           "Sicherheitsteam von Debian bestätigt sie",
           "n_early": "Eine Korrektur für {cves}, das die CISA als derzeit ausgenutzt führt, wurde vorgezogen "
           "installiert: Das Sicherheitsteam von Debian hat sie bestätigt."},
    "ja": {"wait_note": "待っている間、セキュリティ修正はDebianのセキュリティチーム（OSV.dev経由）と、CISAの現在悪用されている脆弱性の一覧で確認します。送るのはCVE番号だけです。確認された修正は待ちません。",
           "unconfirmed": "独立した情報源で確認できなかったため、ほかと同じように待ちます",
           "no_cve": "確認するCVEが示されていないため、ほかと同じように待ちます",
           "early_confirmed": "待ちません：Debianのセキュリティチームが修正を確認しています（{cves}）",
           "early_kev": "最初に入れます：CISAが現在悪用されていると挙げている{cves}を修正し、Debianのセキュリティチームが確認しています",
           "n_early": "CISAが現在悪用されていると挙げている{cves}の修正を先にインストールしました：Debianのセキュリティチームが確認しています。"},
}
for _code, _extra in WORDS_HOLDS.items():
    WORDS[_code].update(_extra)
    WORDS[_code].update(WORDS_EARLY[_code])



def words(key: str, code: str | None = None, **fill) -> str:
    text = WORDS.get(code or offline.lang(), WORDS["en"])[key]
    return text.format(**fill) if fill else text


def read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def held(item: dict, settings: dict, now: float) -> str:
    """Why an update is held as the settings now stand (the same rule as the admin mechanism's apply_holds, so a change
    shows before it's saved): "update" or "program" (the person's own), "waiting", or ""."""
    name = item["name"].split(":", 1)[0]
    own = {(h["name"], h["version"]) for h in settings.get("own", [])}
    if (name, item["version"]) in own:
        return "update"
    if (name, "") in own:
        return "program"
    days = settings.get("hold_days", 0)
    if days and not item.get("early") and now < item.get("seen", now) + days * DAY:
        return "waiting"
    return ""


def hold(settings: dict, item: dict, kind: str) -> dict:
    """The settings with a hold of the person's own added ("update", "program"), or theirs on this item released ("")."""
    name = item["name"].split(":", 1)[0]
    own = [h for h in settings.get("own", []) if h["name"] != name or h["version"] not in ("", item["version"])]
    if kind:
        own.append({"name": name, "version": item["version"] if kind == "update" else ""})
    return dict(settings, own=own)


def when(ts: float) -> str:
    return time.strftime("%a %d %b %H:%M", time.localtime(ts))


def reason(item: dict, why: str, settings: dict, code: str | None = None) -> str:
    """The line under an update: why it's held, or why a security fix doesn't wait (D89's emergency path)."""
    if why == "waiting":
        line = words("held_waiting", code, when=when(item.get("seen", 0) + settings.get("hold_days", 0) * DAY))
        if item.get("unconfirmed"):
            line += ". " + words("unconfirmed" if item.get("cves") else "no_cve", code)
        return line
    if why in ("update", "program"):
        return words(f"held_{why}", code)
    if item.get("early") and settings.get("hold_days"):
        return words(f"early_{item['early']}", code, cves=", ".join(item.get("confirmed", [])[:3]))
    return ""


def last_auto(status: dict, code: str | None = None) -> str:
    """The daily run's last result, in a line ("" before its first run)."""
    if not status.get("ts"):
        return ""
    if status.get("error") and status["error"] != "busy":
        return words("last_auto_err", code, when=when(status["ts"]), why=words(f"why_{status['error']}", code))
    return words("last_auto", code, when=when(status["ts"]), n=len(status.get("installed", [])),
                 held=len(status.get("held", [])))


def notices(status: dict, noticed: dict, code: str | None = None) -> tuple[list[str], dict]:
    """What the daily run needs the person to know and hasn't told them yet: (texts, what's now been told). A CISA
    warning comes once per update; the rest once per run."""
    texts, told = [], {"run": noticed.get("run", 0), "kev": list(noticed.get("kev", []))}
    if status.get("ts") and status["ts"] > told["run"]:
        told["run"] = status["ts"]
        if status.get("signature"):
            texts.append(words("n_genuine", code))
        elif status.get("error") in ("install", "after"):
            texts.append(words("n_stopped", code))
        for e in status.get("early", []):
            if e.get("why") == "kev" and f"{e['name']}={e['version']}" in status.get("installed", []):
                texts.append(words("n_early", code, cves=", ".join(e.get("cves", [])[:3])))
        if status.get("restart"):
            texts.append(words("n_restart", code))
    for k in status.get("kev", []):
        key = f"{k['name']}={k['version']}"
        if key not in told["kev"]:
            told["kev"].append(key)
            texts.append(words("n_kev", code, cves=", ".join(k["cves"][:3])))
    told["kev"] = told["kev"][-200:]
    return texts, told


def noticed_path() -> str:
    return os.path.join(offline.state_dir(), "updates-noticed.json")


def notify_once() -> int:
    """cinminai-updates --notices: the panel icon runs it at login and every few hours."""
    path = noticed_path()
    texts, told = notices(read_json(STATUS, {}), read_json(path, {}))
    for text in texts:
        try:
            subprocess.run(["notify-send", "-i", "system-software-update", words("title"), text], timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(told, f)
    return 0


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
    saved = read_json(SETTINGS, {})
    saved = {"hold_days": saved.get("hold_days", 0), "auto": saved.get("auto", False), "own": saved.get("own", [])}
    state = {"plan": None, "online": False, "job": "", "sources": [], "rows": [], "busy": False,
             "saved": saved, "settings": json.loads(json.dumps(saved))}

    win = Gtk.Window(title=words("title", code))
    win.set_default_size(620, 640)
    win.set_border_width(16)
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    win.add(outer)
    head = Gtk.Label(xalign=0, wrap=True)
    head.get_style_context().add_class("title")
    note = Gtk.Label(xalign=0, wrap=True, max_width_chars=70)
    held_count = Gtk.Label(xalign=0, wrap=True, max_width_chars=70)
    outer.pack_start(head, False, False, 0)
    outer.pack_start(note, False, False, 0)
    outer.pack_start(held_count, False, False, 0)
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
    # the holds and automatic updates (D89): optional, off until the person turns them on
    wait_row = Gtk.Box(spacing=6)
    wait_check = Gtk.CheckButton(label=words("wait_check", code))
    days = Gtk.SpinButton.new_with_range(1, 60, 1)
    days.set_value(state["saved"]["hold_days"] or 2)
    wait_row.pack_start(wait_check, False, False, 0)
    wait_row.pack_start(days, False, False, 0)
    wait_row.pack_start(Gtk.Label(label=words("wait_days", code), xalign=0, wrap=True), False, False, 0)
    wait_note = Gtk.Label(label=words("wait_note", code), xalign=0, wrap=True, max_width_chars=80)
    wait_note.get_style_context().add_class("dim-label")
    auto_check = Gtk.CheckButton(label=words("auto", code))
    save_row = Gtk.Box(spacing=8)
    save = Gtk.Button(label=words("save", code))
    save_note = Gtk.Label(xalign=0, wrap=True)
    save_note.get_style_context().add_class("dim-label")
    save_row.pack_start(save, False, False, 0)
    save_row.pack_start(save_note, False, False, 0)
    auto_line = Gtk.Label(xalign=0, wrap=True)
    auto_line.get_style_context().add_class("dim-label")
    for w in (wait_row, wait_note, auto_check, save_row, auto_line):
        outer.pack_start(w, False, False, 0)
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
        held_count.set_text("")
        held_count.hide()

    def busy(on: bool) -> None:
        state["busy"] = on
        again.set_sensitive(not on)
        install.set_sensitive(not on and bool(state["plan"] and state["plan"]["updates"]))
        snap.set_sensitive(not on)
        for w in (wait_row, auto_check):
            w.set_sensitive(not on)
        save.set_sensitive(not on and state["settings"] != state["saved"])

    def show_plan(p: dict) -> None:
        state["plan"] = p
        if p.get("settings") and state["settings"] == state["saved"]:
            state["saved"] = p["settings"]  # what root has, unless the person is in the middle of a change
            state["settings"] = json.loads(json.dumps(p["settings"]))
            show_settings()
        clear()
        again.set_label(words("again", code))
        head.set_markup(f"<big><b>{GLib.markup_escape_text(headline(p, code))}</b></big>")
        notes = []
        if p["phased"]:
            notes.append(words("phased", code, n=p["phased"]))
        if p["remove"]:
            notes.append(words("removes", code, names=", ".join(p["remove"][:5])))
        if p.get("kev_checked") is False:
            notes.append(words("kev_unknown", code))
        note.set_text("\n".join(notes))
        for item in sorted(p["updates"], key=lambda i: (i.get("early") != "kev", not i["security"], i["name"])):
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
            why = Gtk.Label(xalign=0, wrap=True)
            text.pack_start(top, False, False, 0)
            text.pack_start(small, False, False, 0)
            text.pack_start(why, False, False, 0)
            if item.get("kev"):
                kev = Gtk.Label(xalign=0, wrap=True)
                kev.set_markup("<b>⚠ " + GLib.markup_escape_text(
                    words("kev", code, cves=", ".join(item["kev"][:3]))) + "</b>")
                text.pack_start(kev, False, False, 0)
            menu = Gtk.Menu()
            for kind in ("update", "program", ""):
                entry = Gtk.MenuItem(label=words(f"hold_{kind}" if kind else "release", code))
                entry.connect("activate", lambda _m, it=item, k=kind: change(hold(state["settings"], it, k)))
                menu.append(entry)
            menu.show_all()
            hold_button = Gtk.MenuButton(label=words("hold_menu", code), popup=menu)
            hold_button.set_relief(Gtk.ReliefStyle.NONE)
            row.pack_start(tick, False, False, 0)
            row.pack_start(text, True, True, 0)
            row.pack_start(hold_button, False, False, 0)
            listing.add(row)
            state["rows"].append((tick, item, why))
        mark_held(fresh=True)
        ready = timeshift_ready()
        snap.set_visible(ready)
        snap.set_active(ready)
        snap_none.set_visible(not ready and bool(p["updates"]))
        listing.show_all()
        count()
        busy(False)

    def chosen() -> list[dict]:
        return [item for tick, item, _ in state["rows"] if tick.get_active()]

    def mark_held(fresh: bool = False) -> None:
        """Each row's hold as the settings now stand; a row whose hold changed is ticked or unticked to match (the
        person can still tick a held one: their call)."""
        now = time.time()
        for tick, item, label in state["rows"]:
            why = held(item, state["settings"], now)
            if fresh or why != item.get("shown_hold"):
                tick.set_active(not why)
            item["shown_hold"] = why
            line = reason(item, why, state["settings"], code)
            label.set_markup(f"<small>{GLib.markup_escape_text(line)}</small>" if line else "")
            label.set_visible(bool(line))
        n = sum(1 for _, item, _ in state["rows"] if item["shown_hold"])
        held_count.set_text(words("held_note", code, n=n) if n else "")
        held_count.set_visible(bool(n))
        count()

    def show_settings() -> None:
        st = state["settings"]
        state["quiet"] = True
        wait_check.set_active(bool(st["hold_days"]))
        if st["hold_days"]:
            days.set_value(st["hold_days"])
        days.set_sensitive(bool(st["hold_days"]))
        wait_note.set_visible(bool(st["hold_days"]))
        auto_check.set_active(st["auto"])
        state["quiet"] = False
        dirty = st != state["saved"]
        save.set_visible(dirty or bool(save_note.get_text()))
        save.set_sensitive(dirty and not state["busy"])
        auto_line.set_text(last_auto(read_json(STATUS, {}), code))
        auto_line.set_visible(bool(auto_line.get_text()))

    def change(settings: dict) -> None:
        state["settings"] = settings
        save_note.set_text(words("unsaved", code) if settings != state["saved"] else "")
        show_settings()
        mark_held()

    def settings_edited(*_) -> None:
        if state.get("quiet"):
            return
        days.set_sensitive(wait_check.get_active())
        change(dict(state["settings"], hold_days=int(days.get_value()) if wait_check.get_active() else 0,
                    auto=auto_check.get_active()))

    def save_settings(*_) -> None:
        wanted = json.loads(json.dumps(state["settings"]))
        save.set_sensitive(False)

        def done(out, error) -> None:
            if error:
                save_note.set_text(failure(error, code))
                save.set_sensitive(True)
                return
            state["saved"] = wanted
            save_note.set_text(words("saved", code))
            show_settings()
        admin("SetUpdateSettings", (json.dumps(wanted),), "(s)", done, interactive=True)

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
            p = out or {"updates": [], "new": [], "remove": [], "phased": 0}
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
    wait_check.connect("toggled", settings_edited)
    days.connect("value-changed", settings_edited)
    auto_check.connect("toggled", settings_edited)
    save.connect("clicked", save_settings)
    install.connect("clicked", run_install)
    win.connect("delete-event", leave)
    win.show_all()
    snap.hide()
    snap_none.hide()
    install.hide()
    show_settings()
    if offline.on():
        head.set_markup(f"<big><b>{GLib.markup_escape_text(words('title', code))}</b></big>")
        note.set_text(words("offline", code))
        again.set_label(words("go_online", code))
    else:
        check()
    Gtk.main()
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv and argv[0] == "--notices":
        return notify_once()
    return window()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
