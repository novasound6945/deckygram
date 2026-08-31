"""Switching between destinations, and erasing one.

Both credentials live side by side, so the rules about which one is
active - and what happens when the active one is erased - are worth
pinning down.
"""

import unittest

from . import context  # noqa: F401
from deckygram import destinations

TG = {"token": "123:AA", "chat_id": "42"}
DC = {"webhook_url": "https://discord.com/api/webhooks/1/tok"}


def both(**over):
    return dict(TG, **dict(DC, **over))


class TestBothStored(unittest.TestCase):
    def test_each_is_configured_independently(self):
        s = both()
        self.assertTrue(destinations.build(dict(s, destination="telegram")).configured())
        self.assertTrue(destinations.build(dict(s, destination="discord")).configured())

    def test_telegram_alone(self):
        s = dict(TG, destination="discord")
        self.assertFalse(destinations.build(s).configured())
        self.assertTrue(destinations.build(dict(s, destination="telegram")).configured())

    def test_discord_alone(self):
        s = dict(DC, destination="telegram")
        self.assertFalse(destinations.build(s).configured())
        self.assertTrue(destinations.build(dict(s, destination="discord")).configured())


def forget(settings, dest):
    """The rules main.py applies - mirrored here to keep them honest."""
    s = dict(settings)
    if dest == destinations.TELEGRAM:
        s["token"] = ""
        s["chat_id"] = ""
    else:
        s["webhook_url"] = ""
    if s.get("destination") == dest:
        other = (destinations.DISCORD if dest == destinations.TELEGRAM
                 else destinations.TELEGRAM)
        s["destination"] = (other if destinations.build(
            dict(s, destination=other)).configured() else dest)
    return s


class TestForgetting(unittest.TestCase):
    def test_erasing_telegram_clears_both_of_its_fields(self):
        s = forget(both(destination="discord"), "telegram")
        self.assertEqual(s["token"], "")
        self.assertEqual(s["chat_id"], "")

    def test_the_other_destination_survives(self):
        s = forget(both(destination="discord"), "telegram")
        self.assertTrue(destinations.build(dict(s, destination="discord")).configured())

    def test_erasing_the_active_one_falls_back_to_the_other(self):
        s = forget(both(destination="telegram"), "telegram")
        self.assertEqual(s["destination"], "discord")
        self.assertTrue(destinations.build(s).configured())

    def test_erasing_the_only_one_leaves_it_unconfigured(self):
        s = forget(dict(TG, destination="telegram"), "telegram")
        self.assertFalse(destinations.build(s).configured())

    def test_erasing_the_idle_one_does_not_move_the_active_one(self):
        s = forget(both(destination="discord"), "telegram")
        self.assertEqual(s["destination"], "discord")


if __name__ == "__main__":
    unittest.main()
