"""Tests for birthday UI (list and detail keyboards)."""
import unittest
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from views.message_factory import MessageFactory


class TestBirthdayUi(unittest.TestCase):
    def _birthday(self, birthday_id: int, name: str, birth_date: date):
        return SimpleNamespace(id=birthday_id, name=name, birth_date=birth_date)

    @patch("services.timezone_util.now")
    def test_list_button_labels(self, mock_now):
        mock_now.return_value = datetime(2026, 5, 24, 12, 0)
        birthdays = [
            self._birthday(1, "Anna Müller", date(1996, 5, 25)),
            self._birthday(2, "Bob", date(1988, 1, 2)),
        ]
        labels = [
            MessageFactory.birthday_list_button_label(b) for b in birthdays
        ]
        self.assertEqual(
            labels, ["25.05. Anna Müller (30)", "02.01. Bob (39)"]
        )

    def test_create_birthdays_view_has_callbacks(self):
        birthdays = [self._birthday(42, "Anna", date(1996, 5, 25))]
        text, keyboard = MessageFactory.create_birthdays_view(birthdays)

        self.assertIn("Geburtstage", text)
        all_data = [
            btn.callback_data
            for row in keyboard.inline_keyboard
            for btn in row
        ]
        self.assertEqual(all_data, ["view_bday_42"])

    def test_empty_birthdays_view(self):
        text, keyboard = MessageFactory.create_birthdays_view([])

        self.assertIn("Noch keine Geburtstage", text)
        self.assertEqual(len(keyboard.inline_keyboard), 0)

    def test_detail_keyboard_has_required_buttons(self):
        keyboard = MessageFactory.create_birthday_detail_keyboard(7)
        all_data = [
            btn.callback_data
            for row in keyboard.inline_keyboard
            for btn in row
        ]
        self.assertIn("edit_bday_name_7", all_data)
        self.assertIn("edit_bday_date_7", all_data)
        self.assertIn("del_bday_7", all_data)
        self.assertIn("list_birthdays", all_data)

    def test_birthday_detail_text(self):
        birthday = self._birthday(1, "Anna Müller", date(1996, 5, 25))
        text = MessageFactory.birthday_detail_text(birthday)

        self.assertIn("Anna Müller", text)
        self.assertIn("25.05.1996", text)
        self.assertIn("Alter:", text)
