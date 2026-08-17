import unittest

from template_patch import patch


class PatchTest(unittest.TestCase):
    def test_replaces_placeholder_when_present(self):
        result = patch("url={{URL}}\n", {"{{URL}}": "https://erp.example.com"})
        self.assertEqual(result, "url=https://erp.example.com\n")

    def test_replaces_multiple_placeholders_in_one_pass(self):
        result = patch(
            "url={{URL}}\ntoken={{TOKEN}}\n",
            {"{{URL}}": "https://erp.example.com", "{{TOKEN}}": "abc123"},
        )
        self.assertEqual(result, "url=https://erp.example.com\ntoken=abc123\n")

    def test_raises_when_placeholder_missing(self):
        with self.assertRaises(ValueError):
            patch("url=fixo\n", {"{{URL}}": "https://erp.example.com"})

    def test_does_not_apply_any_substitution_when_one_placeholder_is_missing(self):
        text = "url={{URL}}\ntoken=fixo\n"
        with self.assertRaises(ValueError):
            patch(text, {"{{URL}}": "https://erp.example.com", "{{TOKEN}}": "abc123"})

    def test_error_message_lists_the_missing_placeholder(self):
        with self.assertRaisesRegex(ValueError, r"\{\{TOKEN\}\}"):
            patch("token=fixo\n", {"{{TOKEN}}": "abc123"})


if __name__ == "__main__":
    unittest.main()
