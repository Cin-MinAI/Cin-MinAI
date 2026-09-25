"""Headless LibreOffice for tests (M0 spike): a throwaway profile in /tmp, a UNO pipe, sample docs.

The user's own LibreOffice profile and any LibreOffice they have open are never touched: a
different UserInstallation means a separate LibreOffice process.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time

import uno
from com.sun.star.beans import PropertyValue

PIPE = f"cinminai_lo_{os.getpid()}"


def prop(name, value) -> PropertyValue:
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


class Office:
    def __init__(self, extension: str | None = None, visible: bool = False) -> None:
        self.profile = tempfile.mkdtemp(prefix="cinminai-lo-profile-")
        env = f"-env:UserInstallation=file://{self.profile}"
        if extension:
            r = subprocess.run(["unopkg", "add", "--suppress-license", env, extension],
                               capture_output=True, text=True, timeout=120)
            if r.returncode:
                raise RuntimeError(f"unopkg add failed: {r.stdout}{r.stderr}")
        args = ["soffice", env, "--norestore", "--nologo", "--nodefault", "--nolockcheck",
                f"--accept=pipe,name={PIPE};urp;StarOffice.ComponentContext"]
        if not visible:
            args[1:1] = ["--headless", "--invisible"]
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
        for _ in range(100):
            try:
                self.ctx = resolver.resolve(f"uno:pipe,name={PIPE};urp;StarOffice.ComponentContext")
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("LibreOffice didn't come up")
        self.smgr = self.ctx.ServiceManager
        self.desktop = self.smgr.createInstanceWithContext("com.sun.star.frame.Desktop", self.ctx)

    def new(self, factory: str):
        return self.desktop.loadComponentFromURL(f"private:factory/{factory}", "_blank", 0, ())

    def dispatch(self, doc, url: str) -> None:
        helper = self.smgr.createInstanceWithContext("com.sun.star.frame.DispatchHelper", self.ctx)
        helper.executeDispatch(doc.getCurrentController().getFrame(), url, "", 0, ())

    def close(self) -> None:
        try:
            self.desktop.terminate()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)


# --- sample documents --------------------------------------------------------------------------

WRITER_TEXT = [
    ("Heading 1", "Project Kestrel"),
    ("Standard", "Kestrel is a small weather station built on a Raspberry Pi Pico W."),
    ("Heading 2", "Hardware"),
    ("Standard", "The sensor board uses a BME280 over I2C and a rain gauge on GPIO 15."),
    ("Heading 2", "Software"),
    ("Standard", "teh firmware is writen in MicroPython and posts readings every five minuts."),
    ("Heading 1", "Results"),
    ("Standard", "After two weeks the station logged 4,032 readings with no gaps."),
]


def writer_doc(office: Office):
    doc = office.new("swriter")
    text = doc.getText()
    cur = text.createTextCursor()
    for i, (style, para) in enumerate(WRITER_TEXT):
        if i:
            text.insertControlCharacter(cur, 0, False)  # PARAGRAPH_BREAK
        cur.setPropertyValue("ParaStyleName", style)
        text.insertString(cur, para, False)
    return doc


def select_paragraph(doc, index: int) -> None:
    enum = doc.getText().createEnumeration()
    for i in range(index + 1):
        p = enum.nextElement()
    doc.getCurrentController().select(p)


CALC_DATA = [
    ("Month", "Rain mm", "Max °C"),
    ("Jan", 78, 6.5), ("Feb", 61, 7.9), ("Mar", 55, 11.2), ("Apr", 48, 14.8),
    ("May", 52, 18.9), ("Jun", 45, 22.4),
]


def calc_doc(office: Office):
    doc = office.new("scalc")
    sheet = doc.getSheets().getByIndex(0)
    sheet.setName("Weather")
    for r, row in enumerate(CALC_DATA):
        for c, v in enumerate(row):
            cell = sheet.getCellByPosition(c, r)
            if isinstance(v, str):
                cell.setString(v)
            else:
                cell.setValue(v)
    sheet.getCellRangeByName("A8").setString("Total")
    sheet.getCellRangeByName("B8").setFormula("=SUM(B2:B7)")
    doc.getCurrentController().select(sheet.getCellRangeByName("B8"))
    return doc


def impress_doc(office: Office):
    doc = office.new("simpress")
    pages = doc.getDrawPages()
    while pages.getCount() < 2:
        pages.insertNewByIndex(pages.getCount() - 1)
    for i, (t, b) in enumerate([("Kestrel weather station", "Two weeks of data"),
                                 ("Hardware", "Pico W\nBME280\nRain gauge")]):
        page = pages.getByIndex(i)
        page.setPropertyValue("Layout", 0 if i == 0 else 1)  # 0: title slide, 1: title + content
        for s in range(page.getCount()):
            shape = page.getByIndex(s)
            kind = shape.getShapeType()
            if kind == "com.sun.star.presentation.TitleTextShape":
                shape.setString(t)
            elif kind in ("com.sun.star.presentation.SubtitleShape", "com.sun.star.presentation.OutlinerShape"):
                shape.setString(b)
    return doc
