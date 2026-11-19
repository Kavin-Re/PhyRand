"""Static checks on the browser client: it must run under ``default-src 'self'``."""

import re
import unittest

from .helpers import REPO_ROOT

STATIC = REPO_ROOT / "static"


class WebClientTests(unittest.TestCase):
    def setUp(self):
        self.html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.fernet = (STATIC / "fernet.js").read_text(encoding="utf-8")

    def test_no_third_party_resources(self):
        for name, text in (("index.html", self.html), ("app.js", self.js)):
            self.assertIsNone(re.search(r"""(src|href)\s*=\s*["'](https?:)?//""", text), name)
        self.assertNotIn("cdnjs", self.html)
        self.assertNotIn("googleapis", self.html)

    def test_no_inline_scripts_or_event_handlers(self):
        self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)[^>]*>", self.html))
        self.assertIsNone(re.search(r"\son[a-z]+\s*=", self.html, re.IGNORECASE))
        self.assertIsNone(re.search(r"\sstyle\s*=", self.html, re.IGNORECASE))
        self.assertNotIn("<style", self.html)

    def test_no_html_string_injection_sinks(self):
        for name, text in (("app.js", self.js), ("fernet.js", self.fernet)):
            for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
                self.assertNotIn(sink, text, f"{sink} in {name}")

    def test_secrets_are_not_persisted_in_the_browser(self):
        for storage in ("localStorage", "sessionStorage", "document.cookie", "indexedDB"):
            # The header comment mentions them; make sure they are never called.
            self.assertIsNone(re.search(rf"{re.escape(storage)}\s*[.\[=(]", self.js), storage)

    def test_mac_is_verified_before_decryption(self):
        verify = self.fernet.index('subtle.verify("HMAC"')
        decrypt = self.fernet.index("subtle.decrypt(")
        self.assertLess(verify, decrypt)

    def test_referenced_assets_exist(self):
        for asset in re.findall(r"""(?:src|href)="([^"]+)\"""", self.html):
            self.assertTrue((STATIC / asset).is_file(), asset)


if __name__ == "__main__":
    unittest.main()
