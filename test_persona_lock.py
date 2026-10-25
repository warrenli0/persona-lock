import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import persona_lock as pl

SAMPLE_HOSTS = "127.0.0.1\tlocalhost\n255.255.255.255\tbroadcasthost\n::1             localhost\n"


class NormalizeDomainTest(unittest.TestCase):
    def test_strips_url_parts(self):
        self.assertEqual(pl.normalize_domain("https://www.Reddit.com/r/foo"), "reddit.com")
        self.assertEqual(pl.normalize_domain("youtube.com:443"), "youtube.com")
        self.assertEqual(pl.normalize_domain("news.ycombinator.com"), "news.ycombinator.com")

    def test_rejects_garbage(self):
        for bad in ["", "localhost", "not a domain", "foo..com"]:
            with self.assertRaises(ValueError):
                pl.normalize_domain(bad)


class HostsFileTest(unittest.TestCase):
    def test_build_and_strip_round_trip(self):
        blocked = pl.build_hosts(SAMPLE_HOSTS, ["reddit.com"])
        self.assertIn("0.0.0.0 reddit.com", blocked)
        self.assertIn("0.0.0.0 www.reddit.com", blocked)
        self.assertTrue(blocked.startswith(SAMPLE_HOSTS))
        self.assertEqual(pl.build_hosts(blocked, []), SAMPLE_HOSTS)

    def test_site_group_blocks_related_domains(self):
        blocked = pl.build_hosts(SAMPLE_HOSTS, ["x.com"])
        for host in ["twitter.com", "www.twitter.com", "api.x.com", "abs.twimg.com",
                     "t.co", "mobile.x.com"]:
            self.assertIn(f"0.0.0.0 {host}\n", blocked)
        # Unrelated domains still only get the domain and common subdomains.
        self.assertEqual(
            pl.expand_hosts(["example.com"]),
            ["example.com", "www.example.com", "m.example.com", "mobile.example.com"],
        )

    def test_rebuild_replaces_section(self):
        once = pl.build_hosts(SAMPLE_HOSTS, ["reddit.com"])
        twice = pl.build_hosts(once, ["x.com"])
        self.assertEqual(twice.count(pl.BEGIN_MARKER), 1)
        self.assertNotIn("reddit.com", twice)
        self.assertIn("0.0.0.0 x.com", twice)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.hosts = tmp / "hosts"
        self.hosts.write_text(SAMPLE_HOSTS)
        patches = [
            mock.patch.object(pl, "HOSTS_PATH", self.hosts),
            mock.patch.object(pl, "CONFIG_DIR", tmp / "config"),
            mock.patch.object(pl, "BLOCKLIST_PATH", tmp / "config" / "blocklist.txt"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_then_remove_with_confirmation(self):
        pl.main(["add", "reddit.com", "https://www.youtube.com/"])
        self.assertEqual(pl.load_blocklist(), ["reddit.com", "youtube.com"])
        self.assertIn("0.0.0.0 youtube.com", self.hosts.read_text())

        with mock.patch("builtins.input", return_value="unblock reddit.com"):
            pl.main(["remove", "reddit.com"])
        self.assertEqual(pl.load_blocklist(), ["youtube.com"])
        self.assertNotIn("reddit.com", self.hosts.read_text())

    def test_remove_kept_when_not_confirmed(self):
        pl.main(["add", "reddit.com"])
        with mock.patch("builtins.input", return_value="y"):
            pl.main(["remove", "reddit.com"])
        self.assertEqual(pl.load_blocklist(), ["reddit.com"])
        self.assertIn("0.0.0.0 reddit.com", self.hosts.read_text())

    def test_removing_everything_restores_original(self):
        pl.main(["add", "reddit.com"])
        pl.main(["remove", "--yes", "reddit.com"])
        self.assertEqual(self.hosts.read_text(), SAMPLE_HOSTS)


if __name__ == "__main__":
    unittest.main()
