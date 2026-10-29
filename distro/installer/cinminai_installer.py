# SPDX-License-Identifier: GPL-3.0-or-later
"""What Cin-MinAI changes in Mint's installer (ubiquity), PLAN D47: one operating system per physical drive, each with
its own start-up files.

Installed as ubiquity/cinminai.py in the live system; patch_ubiquity.py hooks it into ubi-partman.py at build time.

* **A drive of its own, recommended:** the Installation type page says so under its heading, naming the installer's
  own "Erase disk and install" option and encryption box (their words come from the installer, in the person's
  language); our sentences are in the six v1 languages (PLAN D25).
* **Erase disk, preselected on a free drive:** with more than one drive and one of them holding no other system,
  "Erase disk and install" is ticked and that drive is the one offered first. Nothing is erased without the installer's
  own confirmation, as before.
* **The start-up files on the drive being installed:** with "Something else", the bootloader's drive defaults to the
  drive holding the new / partition, not the first drive (Mint's default puts GRUB on Windows' drive).
"""

from __future__ import annotations

import os
import re

RECOMMEND = {
    "en": "Recommended: give Cin-MinAI a drive of its own ({erase}) and keep Windows on its own drive. Unplug the "
          "Windows drive while installing, so nothing touches it.",
    "es": "Recomendado: dale a Cin-MinAI un disco propio ({erase}) y deja Windows en su propio disco. Desconecta el "
          "disco de Windows durante la instalación para que nada lo toque.",
    "pt": "Recomendado: dê ao Cin-MinAI um disco próprio ({erase}) e deixe o Windows no disco dele. Desconecte o "
          "disco do Windows durante a instalação, para que nada mexa nele.",
    "fr": "Recommandé : donnez à Cin-MinAI un disque à lui ({erase}) et gardez Windows sur son propre disque. "
          "Débranchez le disque de Windows pendant l'installation, pour que rien n'y touche.",
    "de": "Empfohlen: Geben Sie Cin-MinAI ein eigenes Laufwerk ({erase}) und lassen Sie Windows auf seinem eigenen "
          "Laufwerk. Trennen Sie das Windows-Laufwerk während der Installation ab, damit nichts daran verändert wird.",
    "ja": "おすすめ: Cin-MinAI には専用のドライブを使い（{erase}）、Windows は別のドライブに残してください。"
          "インストール中は Windows のドライブを外しておくと、何も触れられません。",
}
CRYPTO = {
    "en": "Worth ticking: {crypto}. A lost or stolen drive can't be read without your security key, and the key "
          "can't be recovered if you forget it: write it down.",
    "es": "Vale la pena marcar: {crypto}. Un disco perdido o robado no se puede leer sin tu clave de seguridad, y la "
          "clave no se puede recuperar si la olvidas: anótala.",
    "pt": "Vale a pena marcar: {crypto}. Um disco perdido ou roubado não pode ser lido sem a sua chave de segurança, "
          "e a chave não pode ser recuperada se você a esquecer: anote-a.",
    "fr": "À cocher de préférence : {crypto}. Un disque perdu ou volé ne peut pas être lu sans votre clé de sécurité, "
          "et la clé ne peut pas être récupérée si vous l'oubliez : notez-la.",
    "de": "Empfehlenswert: {crypto}. Ein verlorenes oder gestohlenes Laufwerk kann ohne Ihren Sicherheitsschlüssel "
          "nicht gelesen werden, und der Schlüssel lässt sich nicht wiederherstellen, wenn Sie ihn vergessen: "
          "schreiben Sie ihn auf.",
    "ja": "チェックをおすすめします: {crypto}。なくしたり盗まれたりしたドライブは、セキュリティキーがないと読めません。"
          "キーを忘れると元に戻せないので、書き留めておいてください。",
}


def lang(env: dict | None = None) -> str:
    """The installer's language now (it sets LANG when the person picks one), as one of ours; English otherwise."""
    env = os.environ if env is None else env
    for var in ("LANGUAGE", "LC_ALL", "LANG"):
        code = (env.get(var) or "").split(":")[0][:2].lower()
        if code in RECOMMEND:
            return code
    return "en"


def advice(erase: str, crypto: str = "", code: str | None = None) -> str:
    """The lines under the Installation type heading: a drive of its own, and encryption when it's offered."""
    code = code or lang()
    text = RECOMMEND[code].format(erase=erase.strip())
    if crypto.strip():
        text += "\n" + CRYPTO[code].format(crypto=crypto.strip().rstrip("."))
    return text


def disk_device(partman_id: str) -> str:
    """partman's id for a disk (…/=dev=sda) as its device (/dev/sda)."""
    return partman_id.rsplit("/", 1)[-1].replace("=", "/")


def holds_system(device: str, oslist: dict) -> bool:
    """Does another operating system live on this disk? (os-prober's partitions: /dev/sda1, /dev/nvme0n1p2)"""
    pattern = re.compile(re.escape(device) + r"(p?\d+)$")
    return any(pattern.match(part) for part in oslist)


def free_drive(disks: list[tuple[str, str]], oslist: dict) -> int | None:
    """Of the drives offered (label, partman id), the first that holds no other system; None when every one does or
    there's only one drive (nothing to recommend between)."""
    if len(disks) < 2:
        return None
    for i, (_label, partman_id) in enumerate(disks):
        if not holds_system(disk_device(partman_id), oslist):
            return i
    return None


def root_disk(partitions: dict, to_disk) -> str | None:
    """The drive of the partition that will be mounted at / ("Something else"); None while there's none."""
    for value in partitions.values():
        if value.get("mountpoint") == "/" and "method" in value:
            path = value.get("parted", {}).get("path")
            if path:
                return to_disk(path)
    return None
