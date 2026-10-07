# SPDX-License-Identifier: GPL-3.0-or-later
"""M4 slice 3: the root mechanism's verbs on the one path — always asked, even in Auto; Allow calls the mechanism (which
asks for the password); a cancelled password is a denial, a refusal is a failure with its reason."""

import os
import tempfile
import unittest

from cin_minai.actions import admin
from cin_minai.actions.core import ActionError, Actions, Declined
from cin_minai.actions.record import Record


class AdminThroughThePath(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.calls = []
        self.answer = None              # what the fake mechanism does: None = ok, or an exception to raise
        self.events = []

        def call(method, signature, values, reply):
            self.calls.append((method, signature, values, reply))
            if self.answer:
                raise self.answer
            return "log" if reply else None

        self.actions = Actions(Record(os.path.join(self.dir, "rec.jsonl")), os.path.join(self.dir, "undo"),
                               mode="auto", notify=lambda event, p: self.events.append(event))
        admin.register(self.actions, call=call)

    def events_of(self, p):
        return [e["event"] for e in self.actions.record.of(p.id)]

    def test_every_verb_asks_even_in_auto_mode(self):
        args = {"package": "sl", "unit": "cron.service", "enabled": True, "path": "/etc/sysctl.d/cinminai-a.conf",
                "content": "", "module": "dummy", "argv": ["/usr/sbin/wipefs", "--all", "/dev/loop9"]}
        for name in admin.VERBS:
            with self.subTest(name=name):
                p = self.actions.propose(name, args)
                self.assertEqual(p.state, "waiting")
                self.assertEqual(self.calls, [])        # nothing reaches the mechanism before Allow
                self.actions.answer(p.id, False)
        self.assertEqual(self.calls, [])

    def test_allow_calls_the_mechanism_once_and_records_done_without_undo(self):
        p = self.actions.propose("admin.install_package", {"package": "gimp"}, reason="you asked for a photo editor")
        self.actions.answer(p.id, True)
        self.assertEqual(p.state, "done")
        self.assertIsNone(p.undo)
        self.assertEqual(self.calls, [("InstallPackage", "(s)", ("gimp",), "(s)")])
        self.assertEqual(self.events_of(p), ["proposed", "allowed", "done"])

    def test_cancelled_password_is_a_denial_not_a_failure(self):
        self.answer = Declined("the password wasn't given, so nothing was changed")
        p = self.actions.propose("admin.restart_service", {"unit": "cron.service"})
        self.actions.answer(p.id, True)
        self.assertEqual(p.state, "denied")
        self.assertEqual(self.events_of(p), ["proposed", "allowed", "denied"])
        self.assertEqual(self.actions.record.of(p.id)[-1].get("at"), "password")
        self.assertEqual(self.events[-1], "denied")

    def test_refusal_is_a_failure_with_its_reason(self):
        self.answer = ActionError("the system refused it: sudo is protected")
        p = self.actions.propose("admin.remove_package", {"package": "sudo"})
        self.actions.answer(p.id, True)
        self.assertEqual(p.state, "failed")
        self.assertIn("sudo is protected", str(p.error))

    def test_values_sent_to_the_mechanism(self):
        p = self.actions.propose("admin.write_file", {"path": "/etc/sysctl.d/cinminai-w.conf",
                                                      "content": "vm.swappiness = 10\n"})
        self.actions.answer(p.id, True)
        p = self.actions.propose("admin.set_service_enabled", {"unit": "cron.service", "enabled": False})
        self.actions.answer(p.id, True)
        self.assertEqual(self.calls[0], ("WriteFile", "(sayu)",
                                         ("/etc/sysctl.d/cinminai-w.conf", b"vm.swappiness = 10\n", 0o644), "(s)"))
        self.assertEqual(self.calls[1], ("SetServiceEnabled", "(sb)", ("cron.service", False), None))

    def test_plain_words_and_the_destructive_dialog(self):
        kinds = self.actions.kinds
        self.assertEqual(kinds["admin.install_package"].summary({"package": "gimp"}), "install the program “gimp”")
        self.assertEqual(kinds["admin.run"].summary({"argv": ["/usr/sbin/mkfs.ext4", "-F", "/dev/sdb"]}),
                         "run mkfs.ext4 on /dev/sdb")
        self.assertTrue(kinds["admin.run"].destructive)
        self.assertFalse(kinds["admin.install_package"].destructive)
        self.assertTrue(all(k.lane == "admin" and not k.reversible for n, k in kinds.items() if n.startswith("admin.")))


class MechanismErrors(unittest.TestCase):
    def test_errors_become_plain_outcomes(self):
        e = admin._error(admin.ERR + "Dismissed", "not authorized: dismissed")
        self.assertIsInstance(e, Declined)
        self.assertIsInstance(admin._error(admin.ERR + "NotAuthorized", "denied"), Declined)
        e = admin._error(admin.ERR + "Rejected", "sudo is protected")
        self.assertNotIsInstance(e, Declined)
        self.assertEqual(str(e), "the system refused it: sudo is protected")
        self.assertIsInstance(admin._error("org.freedesktop.DBus.Error.ServiceUnknown", "x"), admin.Unavailable)
        self.assertEqual(str(admin._error(admin.ERR + "Failed", "apt-get exited 100")), "apt-get exited 100")

    def test_the_dbus_prefix_is_taken_off_the_reason(self):
        # as seen live on the test SSD: "the system refused it: GDBus.Error:org.cinminai.Admin1.Error.Rejected: ..."
        remote = admin.ERR + "Rejected"
        self.assertEqual(admin._reason(f"GDBus.Error:{remote}: sudo is protected", remote), "sudo is protected")
        self.assertEqual(admin._reason("Timeout was reached", ""), "Timeout was reached")


class Cards(unittest.TestCase):
    def test_declined_and_failed_cards_say_why(self):
        from cin_minai.sidebar import words
        card = {"summary": "install the program “gimp”", "error": "the system refused it: no such package"}
        self.assertIn("no such package", words.action_failed(card))
        self.assertIn("password wasn't given", words.action_declined({"summary": "restart cron"}))
        lines = [text for text, _ in words.action_lines({"summary": "x", "lane": "admin"})]
        self.assertTrue(any("password" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
