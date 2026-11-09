"""The Visual Library page uses the OS look: the OS app's colours, fonts and theme switch.

Tokens come from web/src/index.css (Classic) and web/src/theme-play.css (Playful, the
default). The page reads the same localStorage key (cos-theme) as web/src/lib/theme.ts.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PAGE = REPO / "campaign-os" / "visualizer.html"
FONTS = REPO / "web" / "public" / "fonts"


class VisualLibraryOsLookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = PAGE.read_text(encoding="utf-8")

    def test_reads_the_os_theme_choice(self):
        self.assertIn("localStorage.getItem('cos-theme')", self.html)
        self.assertIn("html[data-theme='play']", self.html)

    def test_uses_the_os_colours(self):
        css = self.html.lower()
        for token in ("#0a0f1a", "#101727", "#22304d", "#e6ecf5",  # Classic
                      "#f3f0ea", "#ddd7ca", "#1b1a22", "#c6f23a"):  # Playful
            self.assertIn(token, css)
        self.assertNotIn("#c2f64f", css, "old lime desk accent is gone")
        self.assertNotIn("#0c0d10", css, "old near-black is gone")

    def test_uses_the_os_fonts_and_ships_them(self):
        self.assertIn("'DM Sans'", self.html)
        self.assertIn("Bricolage Grotesque", self.html)
        for url in re.findall(r"url\('/app/fonts/([^']+)'\)", self.html):
            self.assertTrue((FONTS / url).is_file(), url)
        self.assertTrue((FONTS / "OFL.txt").is_file(), "font licence ships with the fonts")


if __name__ == "__main__":
    unittest.main()
