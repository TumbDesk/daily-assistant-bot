"""Tests for admin command /version."""
import unittest

from version import __version__
from views.message_factory import MessageFactory


class TestVersionCommand(unittest.TestCase):
    def test_version_is_semver(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_version_text_format(self):
        self.assertEqual(MessageFactory.version_text("0.4.0"), "0.4.0")

    def test_version_text_uses_current_version(self):
        self.assertEqual(MessageFactory.version_text(__version__), __version__)


if __name__ == "__main__":
    unittest.main()
