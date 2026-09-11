import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import lists


class ReadListTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "list.conf"

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_empty_when_file_absent(self):
        self.assertEqual(lists.read_list(str(self.path)), [])

    def test_strips_comments_and_blank_lines(self):
        self.path.write_text(
            "\n# comentário solto\n10.0.0.0/8  # INTERNO\n\n192.168.0.0/16\n"
        )
        self.assertEqual(
            lists.read_list(str(self.path)),
            [("10.0.0.0/8", "INTERNO"), ("192.168.0.0/16", "")],
        )

    def test_materializes_seed_on_first_read_when_file_absent(self):
        seed = [("127.0.0.1", "LOCALHOST")]
        result = lists.read_list(str(self.path), seed=seed)
        self.assertEqual(result, seed)
        self.assertEqual(lists.read_list(str(self.path)), seed)  # persistiu de verdade

    def test_does_not_reseed_once_file_already_exists(self):
        self.path.write_text("8.8.8.8\n")
        result = lists.read_list(str(self.path), seed=[("127.0.0.1", "LOCALHOST")])
        self.assertEqual(result, [("8.8.8.8", "")])


class AddEntryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "list.conf"

    def tearDown(self):
        self._tmp.cleanup()

    def test_appends_when_absent(self):
        result = lists.add_entry(str(self.path), "10.0.0.0/8", comment="INTERNO")
        self.assertTrue(result)
        self.assertEqual(lists.read_list(str(self.path)), [("10.0.0.0/8", "INTERNO")])

    def test_is_idempotent_when_already_present(self):
        lists.add_entry(str(self.path), "10.0.0.0/8")
        result = lists.add_entry(str(self.path), "10.0.0.0/8")
        self.assertFalse(result)
        self.assertEqual(len(lists.read_list(str(self.path))), 1)

    def test_leaves_no_temp_file_behind(self):
        lists.add_entry(str(self.path), "10.0.0.0/8")
        leftovers = list(self.path.parent.glob("*.tmp"))
        self.assertEqual(leftovers, [])

    def test_seeds_the_file_with_defaults_before_appending_when_absent(self):
        # achado ao vivo (produção): técnico adicionou o IP de um cliente
        # confiável (`pvx firewall ip accept`) numa central onde o arquivo
        # ip_accept.conf ainda não existia em disco -- sem seed aqui, o
        # resultado era um arquivo com SÓ o IP novo, apagando (na prática,
        # nunca escrevendo) os IPs base da Phonevox. `apply` sincronizou
        # essa lista incompleta e o técnico perdeu acesso.
        seed = [("127.0.0.1", "LOCALHOST"), ("10.0.0.0/8", "INTERNO")]
        result = lists.add_entry(str(self.path), "203.0.113.9", comment="CLIENTE", seed=seed)
        self.assertTrue(result)
        self.assertEqual(
            lists.read_list(str(self.path)),
            [("127.0.0.1", "LOCALHOST"), ("10.0.0.0/8", "INTERNO"), ("203.0.113.9", "CLIENTE")],
        )

    def test_does_not_reapply_seed_once_file_already_has_content(self):
        self.path.write_text("8.8.8.8\n")
        lists.add_entry(str(self.path), "9.9.9.9", seed=[("127.0.0.1", "LOCALHOST")])
        self.assertEqual(
            lists.read_list(str(self.path)), [("8.8.8.8", ""), ("9.9.9.9", "")],
        )


class RemoveEntryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "list.conf"
        self.path.write_text("10.0.0.0/8  # INTERNO\n192.168.0.0/16\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_removes_existing_entry(self):
        result = lists.remove_entry(str(self.path), "10.0.0.0/8")
        self.assertTrue(result)
        self.assertEqual(lists.read_list(str(self.path)), [("192.168.0.0/16", "")])

    def test_returns_false_when_not_found(self):
        self.assertFalse(lists.remove_entry(str(self.path), "8.8.8.8"))

    def test_seeds_before_removing_when_file_absent(self):
        empty_path = self.path.parent / "empty.conf"
        seed = [("127.0.0.1", "LOCALHOST"), ("10.0.0.0/8", "INTERNO")]
        result = lists.remove_entry(str(empty_path), "10.0.0.0/8", seed=seed)
        self.assertTrue(result)
        self.assertEqual(lists.read_list(str(empty_path)), [("127.0.0.1", "LOCALHOST")])


if __name__ == "__main__":
    unittest.main()
