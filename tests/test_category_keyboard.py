"""Tests for category inline keyboard."""
import unittest
import uuid

from services.types import CategoryDTO
from views.keyboards import build_category_suggestion_keyboard


class TestCategoryKeyboard(unittest.TestCase):
    def test_callback_data_under_64_chars(self):
        event_id = str(uuid.uuid4())
        categories = [CategoryDTO(i, f"Kat{i}") for i in range(1, 7)]
        keyboard = build_category_suggestion_keyboard(event_id, categories)
        for row in keyboard.inline_keyboard:
            for btn in row:
                self.assertLessEqual(len(btn.callback_data), 64)

    def test_top_categories_and_skip_button(self):
        event_id = str(uuid.uuid4())
        categories = [
            CategoryDTO(3, "Einkauf"),
            CategoryDTO(1, "Arbeit"),
            CategoryDTO(2, "Haushalt"),
        ]
        keyboard = build_category_suggestion_keyboard(event_id, categories)
        data = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
        self.assertEqual(data[0], f"cat_set:{event_id}:3")
        self.assertEqual(data[-1], f"cat_skip:{event_id}")
        self.assertEqual(len(data), 4)


if __name__ == "__main__":
    unittest.main()
