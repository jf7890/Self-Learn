import os
import sys
import unittest
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from services.note_sanitizer import sanitize_note_html


class NoteSanitizerTest(unittest.TestCase):
    def test_escapes_scripts_and_event_handlers(self):
        value = '<script>alert(1)</script><p onclick="evil()">safe & sound</p>'
        self.assertEqual(sanitize_note_html(value), 'alert(1)<p>safe &amp; sound</p>')

    def test_keeps_only_safe_links_and_note_images(self):
        safe = sanitize_note_html(
            '<a href="https://example.com" onclick="x">site</a>'
            '<img src="/api/notes/images/abc-123.png" data-width="50" data-align="center" data-caption="A &quot;caption&quot;">'
        )
        self.assertIn('rel="noopener noreferrer"', safe)
        self.assertNotIn("onclick", safe)
        self.assertIn('data-width="50"', safe)
        self.assertNotIn("javascript:", sanitize_note_html('<a href="javascript:alert(1)">bad</a>'))
        self.assertNotIn("evil.example", sanitize_note_html('<img src="https://evil.example/a.png">'))

    def test_rejects_oversized_note(self):
        with self.assertRaises(HTTPException) as raised:
            sanitize_note_html("x" * 250_001)
        self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
