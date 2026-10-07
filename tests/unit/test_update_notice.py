# SPDX-License-Identifier: GPL-3.0-or-later
"""D59, 2026-10-07: an installed update is shown while it waits ("Restart now" in the sidebar) instead of the old
version answering with nothing said; the restart itself still waits for a pause unless the person asks."""

import time
import types
import unittest

try:
    from cin_minai.daemon import service
except ImportError:  # no PyGObject here
    service = None


class FakeWatcher:
    def __init__(self, state):
        self.state, self.seen, self.refused = state, ("v2",), None

    def check(self):
        return self.state


def fake(state="ready", active_ago=0.0, busy=False):
    s = types.SimpleNamespace(watcher=FakeWatcher(state), busy=busy, loading=False, journal=None,
                              active_at=time.monotonic() - active_ago, update_ready=False, changes=[], restarts=0)
    s.changed = lambda *props: s.changes.append(props)

    def restart():
        s.restarts += 1
        return False
    s.restart_for_update = restart
    return s


@unittest.skipIf(service is None, "needs PyGObject")
class UpdateNotice(unittest.TestCase):
    def check(self, s):
        return service.Service.check_update(s)

    def test_waiting_update_is_shown_while_the_person_is_active(self):
        s = fake(active_ago=10)
        self.assertTrue(self.check(s))          # keeps checking: no restart in the middle of use
        self.assertTrue(s.update_ready)
        self.assertEqual(s.changes, [("Status",)])
        self.assertEqual(s.restarts, 0)

    def test_restarts_on_a_pause(self):
        s = fake(active_ago=service.IDLE_BEFORE_RESTART_S + 1)
        self.assertFalse(self.check(s))
        self.assertEqual(s.restarts, 1)

    def test_nothing_shown_without_an_update(self):
        s = fake(state="same")
        self.check(s)
        self.assertFalse(s.update_ready)
        self.assertEqual(s.changes, [])

    def test_a_version_that_did_not_load_is_not_offered_again(self):
        s = fake(active_ago=999)
        s.watcher.refused = s.watcher.seen
        self.check(s)
        self.assertFalse(s.update_ready)
        self.assertEqual(s.restarts, 0)


if __name__ == "__main__":
    unittest.main()
