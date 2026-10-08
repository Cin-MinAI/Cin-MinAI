# SPDX-License-Identifier: GPL-3.0-or-later
"""Installing through the assistant (update 6): a program by name, the recommended graphics driver, and the CUDA engine
(D93) — proposed on the Allow card; the system asks for the password; "No" to the CUDA offer is remembered."""

import os
import tempfile
import types
import unittest
from unittest import mock

from cin_minai.daemon import installs, intent

try:
    from cin_minai.daemon import service
except ImportError:  # no PyGObject
    service = None

PRINT_URIS = """'http://archive.ubuntu.com/ubuntu/pool/universe/b/babl/libbabl_0.1.108-1_amd64.deb' libbabl.deb 455758 MD5Sum:x
'http://archive.ubuntu.com/ubuntu/pool/universe/g/gimp/gimp_2.10_amd64.deb' gimp.deb 4194304 MD5Sum:y
"""


class Checks(unittest.TestCase):
    def test_state(self):
        with mock.patch.object(installs, "_run", side_effect=["install ok installed", ""]):
            self.assertEqual(installs.state("vlc"), "installed")
        with mock.patch.object(installs, "_run", side_effect=["", "vlc:\n  Installed: (none)\n  Candidate: 3.0.20-3"]):
            self.assertEqual(installs.state("vlc"), "available")
        with mock.patch.object(installs, "_run", side_effect=["", "N: Unable to locate package nope"]):
            self.assertEqual(installs.state("nope"), "unknown")
        self.assertEqual(installs.state("rm -rf /"), "unknown")  # not a package name: nothing is even asked

    def test_download_size(self):
        with mock.patch.object(installs, "_run", return_value=PRINT_URIS):
            self.assertEqual(installs.download_mb("gimp"), 4)
        with mock.patch.object(installs, "_run", return_value=""):
            self.assertIsNone(installs.download_mb("gimp"))

    def test_the_recommended_driver(self):
        line = "nvidia-driver-580 linux-modules-nvidia-580-generic-hwe-24.04\n"  # Ian's PC, 2026-10-08
        with mock.patch.object(installs, "_run", return_value=line):
            self.assertEqual(installs.recommended_driver(), "nvidia-driver-580")
        with mock.patch.object(installs, "_run", return_value="nvidia-driver-535, (kernel modules provided by x)\n"):
            self.assertEqual(installs.recommended_driver(), "nvidia-driver-535")
        with mock.patch.object(installs, "_run", return_value=""):
            self.assertEqual(installs.recommended_driver(), "")

    def test_no_is_remembered(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"XDG_DATA_HOME": d}):
            self.assertFalse(installs.declined("cuda"))
            installs.decline("cuda")
            self.assertTrue(installs.declined("cuda"))


class InstallTool(unittest.TestCase):
    def tools(self):
        from cin_minai.daemon.tools import Tools
        return Tools({"software_manager": {"en": "Software Manager"}}, {}, "en")

    def test_a_program_the_sources_have_is_proposed(self):
        actions = mock.Mock(kinds={"admin.install_package": object()})
        actions.propose.return_value = types.SimpleNamespace(id="abc")
        with mock.patch.object(installs, "state", return_value="available"), \
             mock.patch.object(installs, "download_mb", return_value=27), \
             mock.patch("cin_minai.actions.hook.installed", return_value=actions):
            out = self.tools().request_install("GIMP")
        actions.propose.assert_called_once_with("admin.install_package", {"package": "gimp"},
                                                reason="you asked to install gimp (about 27 MB to download)")
        self.assertTrue(out["proposed"])
        self.assertIn("Nothing is installed until", out["note"])

    def test_installed_or_unknown_are_not_proposed(self):
        actions = mock.Mock(kinds={"admin.install_package": object()})
        with mock.patch("cin_minai.actions.hook.installed", return_value=actions):
            with mock.patch.object(installs, "state", return_value="installed"):
                self.assertTrue(self.tools().request_install("vlc")["installed"])
            with mock.patch.object(installs, "state", return_value="unknown"):
                self.assertEqual(self.tools().request_install("photoshop")["open_with"], "Software Manager")
        actions.propose.assert_not_called()


class DriverRequest(unittest.TestCase):
    def test_requests(self):
        for t in ("Install the NVIDIA driver", "can you set up my graphics card driver?",
                  "Instala el controlador de la tarjeta gráfica", "Instalar o driver de vídeo",
                  "Installer le pilote graphique", "Grafiktreiber installieren", "NVIDIAドライバをインストールして"):
            self.assertTrue(intent.driver_request(t), t)

    def test_not_requests(self):
        for t in ("install the printer driver", "update my nvidia driver", "uninstall the nvidia driver",
                  "what driver do I have?", "install VLC"):
            self.assertFalse(intent.driver_request(t), t)


@unittest.skipIf(service is None, "needs PyGObject")
class Daemon(unittest.TestCase):
    def daemon(self):
        actions = mock.Mock(kinds={"admin.install_package": object()})
        return types.SimpleNamespace(actions=actions, guide=types.SimpleNamespace(tools=types.SimpleNamespace(lang="en")))

    def test_the_driver_recipe(self):
        s, text = self.daemon(), []
        with mock.patch.object(installs, "recommended_driver", return_value="nvidia-driver-580"), \
             mock.patch.object(installs, "state", return_value="available"):
            out = service.Service.offer_driver(s, text.append, lambda *a: None)
        s.actions.propose.assert_called_once()
        self.assertEqual(s.actions.propose.call_args.args[1], {"package": "nvidia-driver-580"})
        self.assertIn("click Allow, then type your password", text[0])
        self.assertTrue(out["proposed"])
        for state, rec, words in (("installed", "nvidia-driver-580", "already installed"), ("available", "", "doesn't need")):
            s, text = self.daemon(), []
            with mock.patch.object(installs, "recommended_driver", return_value=rec), \
                 mock.patch.object(installs, "state", return_value=state):
                service.Service.offer_driver(s, text.append, lambda *a: None)
            s.actions.propose.assert_not_called()
            self.assertIn(words, text[0])

    def test_the_cuda_card(self):
        p = types.SimpleNamespace(kind=types.SimpleNamespace(name="admin.install_package"),
                                  args={"package": installs.CUDA_PKG}, error=None)
        s = types.SimpleNamespace(emit=mock.Mock(), card=lambda p, e: {"event": e}, reload_for_cuda=lambda: False)
        with mock.patch.object(service.GLib, "idle_add"), mock.patch.object(service.GLib, "timeout_add_seconds") as later, \
             mock.patch.object(installs, "decline") as decline:
            service.Service.action_notify(s, "denied", p)           # No on the card: remembered
            decline.assert_called_once_with("cuda")
            service.Service.action_notify(s, "denied", types.SimpleNamespace(**{**p.__dict__, "error": Exception()}))
            decline.assert_called_once()                             # a cancelled password: asked again next time
            service.Service.action_notify(s, "done", p)              # installed: onto CUDA at the next pause
            later.assert_called_once()


if __name__ == "__main__":
    unittest.main()
