import unittest

import dialplan


class BuildIncludeLineTest(unittest.TestCase):
    def test_ixcsoft_uses_plain_include(self):
        self.assertEqual(
            dialplan.build_include_line("ixcsoft", "phonevox-macros-atendimento.conf"),
            '#include "phonevox-macros-atendimento.conf"',
        )

    def test_sgp_uses_tryinclude(self):
        self.assertEqual(
            dialplan.build_include_line("sgp", "phonevox-macros-atendimento.conf"),
            '#tryinclude "phonevox-macros-atendimento.conf"',
        )


class AddIncludeIfAbsentTest(unittest.TestCase):
    def test_appends_when_absent(self):
        result = dialplan.add_include_if_absent("[general]\n", '#include "x.conf"')
        self.assertEqual(result, '[general]\n#include "x.conf"\n')

    def test_does_not_duplicate_when_already_present(self):
        text = '[general]\n#include "x.conf"\n'
        self.assertEqual(dialplan.add_include_if_absent(text, '#include "x.conf"'), text)


class AddMohClassIfAbsentTest(unittest.TestCase):
    def test_appends_class_block_when_absent(self):
        result = dialplan.add_moh_class_if_absent("", "sfx-teclado-digitando", "/var/lib/asterisk/moh")
        self.assertIn("[sfx-teclado-digitando]", result)
        self.assertIn("directory=/var/lib/asterisk/moh", result)

    def test_does_not_duplicate_when_class_name_already_present(self):
        text = "[sfx-teclado-digitando]\nmode=files\ndirectory=/custom/path\n"
        result = dialplan.add_moh_class_if_absent(text, "sfx-teclado-digitando", "/var/lib/asterisk/moh")
        self.assertEqual(result, text)


if __name__ == "__main__":
    unittest.main()
