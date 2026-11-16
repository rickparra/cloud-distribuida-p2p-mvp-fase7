import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hosting import HELLO_HTML, HOST_SECONDS, SiteRegistry, html_for_node


class HostingTests(unittest.TestCase):
    def test_site_expires_and_cannot_be_reopened(self):
        clock = [100.0]
        sites = SiteRegistry(now=lambda: clock[0])
        token = sites.start(HOST_SECONDS)
        self.assertEqual(sites.status(token), "ACTIVE")
        clock[0] += HOST_SECONDS
        self.assertEqual(sites.status(token), "EXPIRED")
        self.assertEqual(sites.status(token), "EXPIRED")
        self.assertEqual(sites.status("unknown"), "MISSING")

    def test_manual_stop_closes_site_immediately(self):
        sites = SiteRegistry()
        token = sites.start()
        self.assertTrue(sites.stop(token))
        self.assertEqual(sites.status(token), "EXPIRED")
        self.assertFalse(sites.stop("unknown"))

    def test_hello_world_is_static_html(self):
        self.assertIn("<h1>Hello World</h1>", HELLO_HTML)
        self.assertNotIn("<script", HELLO_HTML)
        self.assertIn("<strong>BR-TEE-01</strong>", html_for_node("BR-TEE-01"))
        self.assertNotIn("__NODE__", html_for_node("BR-TEE-01"))


if __name__ == "__main__":
    unittest.main()
