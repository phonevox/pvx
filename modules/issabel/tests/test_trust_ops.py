import hashlib
import json
import socket
import unittest
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import trust_ops


class Sha256OfTest(unittest.TestCase):
    def test_matches_hashlib_for_a_real_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "f.txt")
            path.write_bytes(b"conteudo de teste")
            expected = hashlib.sha256(b"conteudo de teste").hexdigest()
            self.assertEqual(trust_ops.sha256_of(str(path)), expected)


class StagingTest(unittest.TestCase):
    def test_stage_trust_records_sha256_path_and_ip(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "f.txt")
            path.write_bytes(b"x")
            with patch("trust_ops.local_ip", return_value="203.0.113.5"):
                sha256 = trust_ops.stage(str(path), "trust")
            pending = trust_ops.load_pending()
        self.assertEqual(sha256, hashlib.sha256(b"x").hexdigest())
        self.assertEqual(pending, [
            {"sha256": sha256, "caminho": str(path), "ip_origem": "203.0.113.5", "acao": "trust"},
        ])

    def test_staging_the_same_path_again_replaces_the_previous_entry(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "f.txt")
            path.write_bytes(b"x")
            with patch("trust_ops.local_ip", return_value="1.1.1.1"):
                trust_ops.stage(str(path), "trust")
                trust_ops.stage(str(path), "untrust")
            pending = trust_ops.load_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["acao"], "untrust")

    def test_clear_pending_empties_the_list(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "f.txt")
            path.write_bytes(b"x")
            trust_ops.stage(str(path), "trust")
            trust_ops.clear_pending()
        self.assertEqual(trust_ops.load_pending(), [])

    def test_remove_pending_without_paths_clears_everything_and_returns_the_count(self):
        with TemporaryDirectory() as tmp:
            for name in ("a.txt", "b.txt"):
                Path(tmp, name).write_bytes(b"x")
                trust_ops.stage(str(Path(tmp, name)), "trust")
            removed = trust_ops.remove_pending()
        self.assertEqual(removed, 2)
        self.assertEqual(trust_ops.load_pending(), [])

    def test_remove_pending_with_paths_only_removes_those(self):
        with TemporaryDirectory() as tmp:
            paths = [str(Path(tmp, name)) for name in ("a.txt", "b.txt")]
            for p in paths:
                Path(p).write_bytes(b"x")
                trust_ops.stage(p, "trust")
            removed = trust_ops.remove_pending([paths[0]])
            remaining = trust_ops.load_pending()
        self.assertEqual(removed, 1)
        self.assertEqual([i["caminho"] for i in remaining], [paths[1]])

    def test_remove_pending_with_an_unknown_path_removes_nothing(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "f.txt")
            path.write_bytes(b"x")
            trust_ops.stage(str(path), "trust")
            removed = trust_ops.remove_pending(["/does/not/exist"])
        self.assertEqual(removed, 0)
        self.assertEqual(len(trust_ops.load_pending()), 1)

    def test_load_pending_is_empty_when_nothing_was_ever_staged(self):
        self.assertEqual(trust_ops.load_pending(), [])


class LocalIpTest(unittest.TestCase):
    def test_returns_the_outbound_socket_address(self):
        mock_sock = Mock()
        mock_sock.getsockname.return_value = ("192.0.2.9", 54321)
        mock_sock.__enter__ = Mock(return_value=mock_sock)
        mock_sock.__exit__ = Mock(return_value=False)
        with patch("trust_ops.socket.socket", return_value=mock_sock):
            self.assertEqual(trust_ops.local_ip(), "192.0.2.9")

    def test_falls_back_when_there_is_no_network(self):
        with patch("trust_ops.socket.socket", side_effect=OSError("sem rede")):
            self.assertEqual(trust_ops.local_ip(), "desconhecido")


def _urlopen_response(payload):
    response = Mock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    return response


class FetchRemoteTrustTest(unittest.TestCase):
    def test_uses_the_default_url_and_pvx_namespace_when_none_is_given(self):
        with patch("trust_ops.urllib.request.urlopen", return_value=_urlopen_response({"items": []})) as mock_urlopen:
            trust_ops.fetch_remote_trust()
        self.assertEqual(
            mock_urlopen.call_args.args[0], f"{trust_ops.DEFAULT_URL}/pvx/trust.json",
        )

    def test_fetches_and_caches_the_remote_items(self):
        with patch("trust_ops.urllib.request.urlopen", return_value=_urlopen_response({"items": [{"sha256": "a", "caminho": "/x"}]})):
            items = trust_ops.fetch_remote_trust("http://example.test")
        self.assertEqual(items, [{"sha256": "a", "caminho": "/x"}])
        self.assertEqual(trust_ops.load_cached_trust(), [{"sha256": "a", "caminho": "/x"}])

    def test_falls_back_to_the_last_cached_copy_when_the_network_fails(self):
        with patch("trust_ops.urllib.request.urlopen", return_value=_urlopen_response({"items": [{"sha256": "a", "caminho": "/x"}]})):
            trust_ops.fetch_remote_trust("http://example.test")

        with patch("trust_ops.urllib.request.urlopen", side_effect=urllib.error.URLError("sem rede")):
            items = trust_ops.fetch_remote_trust("http://example.test")
        self.assertEqual(items, [{"sha256": "a", "caminho": "/x"}])

    def test_returns_empty_when_the_network_fails_and_there_is_no_cache(self):
        with patch("trust_ops.urllib.request.urlopen", side_effect=urllib.error.URLError("sem rede")):
            items = trust_ops.fetch_remote_trust("http://example.test")
        self.assertEqual(items, [])


class MergedTrustedItemsTest(unittest.TestCase):
    # a propósito: trust de rede (já publicado, vale pra toda central) e
    # trust local (só pendente nesta central, ainda não publicado) são
    # coisas DIFERENTES -- a origem precisa sobreviver na mescla pra quem
    # exibe poder avisar qual delas suprimiu um achado.
    def test_combines_remote_and_locally_pending_trust_tagging_the_origin(self):
        with patch("trust_ops.fetch_remote_trust", return_value=[{"sha256": "a", "caminho": "/remote.php"}]), \
             patch("trust_ops.load_pending", return_value=[
                 {"sha256": "b", "caminho": "/pending.php", "ip_origem": "x", "acao": "trust"},
             ]):
            merged = trust_ops.merged_trusted_items("http://example.test")
        self.assertEqual(merged, {
            "/remote.php": {"sha256": "a", "origem": "remoto"},
            "/pending.php": {"sha256": "b", "origem": "local"},
        })

    def test_a_local_pending_trust_for_a_path_already_remote_overrides_as_local(self):
        # a central ainda não sabe se o publish vai dar certo -- até lá, o
        # que está pendente localmente é a fonte da verdade pra ela mesma.
        with patch("trust_ops.fetch_remote_trust", return_value=[{"sha256": "a", "caminho": "/x.php"}]), \
             patch("trust_ops.load_pending", return_value=[
                 {"sha256": "a", "caminho": "/x.php", "ip_origem": "x", "acao": "trust"},
             ]):
            merged = trust_ops.merged_trusted_items("http://example.test")
        self.assertEqual(merged, {"/x.php": {"sha256": "a", "origem": "local"}})

    def test_passes_through_no_url_so_fetch_remote_trust_falls_back_to_the_default(self):
        with patch("trust_ops.fetch_remote_trust", return_value=[]) as mock_fetch, \
             patch("trust_ops.load_pending", return_value=[
                 {"sha256": "b", "caminho": "/pending.php", "ip_origem": "x", "acao": "trust"},
             ]):
            merged = trust_ops.merged_trusted_items()
        mock_fetch.assert_called_once_with(None)
        self.assertEqual(merged, {"/pending.php": {"sha256": "b", "origem": "local"}})

    def test_a_pending_untrust_removes_an_already_remote_trusted_path(self):
        with patch("trust_ops.fetch_remote_trust", return_value=[{"sha256": "a", "caminho": "/x.php"}]), \
             patch("trust_ops.load_pending", return_value=[
                 {"sha256": "a", "caminho": "/x.php", "ip_origem": "x", "acao": "untrust"},
             ]):
            merged = trust_ops.merged_trusted_items("http://example.test")
        self.assertEqual(merged, {})


class AnnotateFindingsTest(unittest.TestCase):
    def test_annotates_a_finding_with_the_path_and_the_origin_of_the_trust(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "shell.php")
            path.write_bytes(b"conteudo")
            sha256 = hashlib.sha256(b"conteudo").hexdigest()
            findings = [{"sev": "HIGH", "class": "webshell", "msg": f"arquivo suspeito: {path}"}]
            trusted = {str(path): {"sha256": sha256, "origem": "remoto"}}
            annotated = trust_ops.annotate_findings(findings, trusted)
        self.assertEqual(annotated, [(findings[0], (str(path), "remoto"))])

    def test_never_removes_a_finding_from_the_result_even_when_trusted(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "shell.php")
            path.write_bytes(b"conteudo")
            sha256 = hashlib.sha256(b"conteudo").hexdigest()
            findings = [{"sev": "HIGH", "class": "webshell", "msg": f"arquivo suspeito: {path}"}]
            trusted = {str(path): {"sha256": sha256, "origem": "local"}}
            annotated = trust_ops.annotate_findings(findings, trusted)
        self.assertEqual(len(annotated), len(findings))

    def test_does_not_mark_trusted_when_the_file_changed_since_being_trusted(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "shell.php")
            path.write_bytes(b"conteudo novo")
            stale_sha256 = hashlib.sha256(b"conteudo velho").hexdigest()
            findings = [{"sev": "HIGH", "class": "webshell", "msg": f"arquivo suspeito: {path}"}]
            trusted = {str(path): {"sha256": stale_sha256, "origem": "local"}}
            annotated = trust_ops.annotate_findings(findings, trusted)
        self.assertEqual(annotated, [(findings[0], None)])

    def test_findings_unrelated_to_any_trusted_path_are_never_marked(self):
        findings = [{"sev": "CRIT", "class": "miner", "msg": "processo de mineracao: pid=123"}]
        trusted = {"/etc/foo.php": {"sha256": "a" * 64, "origem": "remoto"}}
        annotated = trust_ops.annotate_findings(findings, trusted)
        self.assertEqual(annotated, [(findings[0], None)])


class PublishTest(unittest.TestCase):
    def test_raises_when_nothing_is_pending(self):
        with self.assertRaises(trust_ops.TrustError):
            trust_ops.publish("pass")

    def test_posts_the_pending_items_with_basic_auth_and_clears_pending_on_success(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "f.txt")
            path.write_bytes(b"x")
            trust_ops.stage(str(path), "trust", ip_origem="203.0.113.5")

            with patch("trust_ops.urllib.request.urlopen", return_value=_urlopen_response({"ok": True, "aplicados": 1, "total": 1})) as mock_urlopen:
                result = trust_ops.publish("pass", url="http://example.test", gerado_por="SRV-1")

            self.assertEqual(result, {"ok": True, "aplicados": 1, "total": 1})
            self.assertEqual(trust_ops.load_pending(), [])

            request = mock_urlopen.call_args.args[0]
            self.assertEqual(request.full_url, "http://example.test/pvx/trust")
            self.assertTrue(request.headers["Authorization"].startswith("Basic "))
            body = json.loads(request.data)
            self.assertEqual(body["gerado_por"], "SRV-1")
            self.assertEqual(len(body["itens"]), 1)

    def test_uses_the_default_url_when_none_is_given(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "f.txt")
            path.write_bytes(b"x")
            trust_ops.stage(str(path), "trust")

            with patch("trust_ops.urllib.request.urlopen", return_value=_urlopen_response({"ok": True, "aplicados": 1, "total": 1})) as mock_urlopen:
                trust_ops.publish("pass")

            request = mock_urlopen.call_args.args[0]
            self.assertEqual(request.full_url, f"{trust_ops.DEFAULT_URL}/pvx/trust")

    def test_raises_a_clean_error_on_http_failure_and_keeps_pending(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "f.txt")
            path.write_bytes(b"x")
            trust_ops.stage(str(path), "trust")

            error = urllib.error.HTTPError("http://example.test/pvx/trust", 401, "Unauthorized", {}, None)
            error.read = lambda: b"senha errada"
            with patch("trust_ops.urllib.request.urlopen", side_effect=error):
                with self.assertRaises(trust_ops.TrustError) as ctx:
                    trust_ops.publish("wrong", url="http://example.test")

        self.assertIn("401", str(ctx.exception))
        self.assertEqual(len(trust_ops.load_pending()), 1)


if __name__ == "__main__":
    unittest.main()
