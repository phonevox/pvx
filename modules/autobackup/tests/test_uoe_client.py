import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

import uoe_client


def _response(payload):
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__.return_value = response
    return response


class LoginTest(unittest.TestCase):
    @patch("uoe_client.urllib.request.urlopen")
    def test_returns_the_token_on_success(self, mock_urlopen):
        mock_urlopen.return_value = _response({"token": "abc123"})
        self.assertEqual(uoe_client.login("root", "secret"), "abc123")

    @patch("uoe_client.urllib.request.urlopen")
    def test_sends_username_and_password_as_json_body(self, mock_urlopen):
        mock_urlopen.return_value = _response({"token": "abc123"})
        uoe_client.login("root", "secret")
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(json.loads(request.data), {"username": "root", "password": "secret"})
        self.assertEqual(request.get_full_url(), "http://uoe.interno.falevox.com.br/v1/users/login")

    @patch("uoe_client.urllib.request.urlopen")
    def test_raises_uoe_error_on_http_failure(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 401, "Unauthorized", {}, fp=MagicMock(read=lambda: b'{"error":"Invalid password"}')
        )
        with self.assertRaises(uoe_client.UOEError) as ctx:
            uoe_client.login("root", "wrong")
        self.assertEqual(ctx.exception.status, 401)
        self.assertIn("Invalid password", ctx.exception.body)


class RegisterTest(unittest.TestCase):
    @patch("uoe_client.urllib.request.urlopen")
    def test_sends_the_bearer_token_and_payload(self, mock_urlopen):
        mock_urlopen.return_value = _response({"username": "empresa", "role": "user"})
        result = uoe_client.register("admintoken", "empresa", "senha-de-teste", "clientes/1-2-empresa")
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer admintoken")
        self.assertEqual(json.loads(request.data), {
            "username": "empresa", "password": "senha-de-teste", "role": "user",
            "root_path": "clientes/1-2-empresa",
        })
        self.assertEqual(result, {"username": "empresa", "role": "user"})

    @patch("uoe_client.urllib.request.urlopen")
    def test_raises_uoe_error_on_failure(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 500, "Internal Server Error", {}, fp=MagicMock(read=lambda: b"Internal Server Error")
        )
        with self.assertRaises(uoe_client.UOEError) as ctx:
            uoe_client.register("admintoken", "empresa", "pw", "clientes/x")
        self.assertEqual(ctx.exception.status, 500)


class DeleteUserTest(unittest.TestCase):
    @patch("uoe_client.urllib.request.urlopen")
    def test_sends_delete_with_the_bearer_token(self, mock_urlopen):
        mock_urlopen.return_value = _response({"message": "User deleted successfully."})
        uoe_client.delete_user("admintoken", "empresa")
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "DELETE")
        self.assertEqual(request.get_full_url(), "http://uoe.interno.falevox.com.br/v1/users/empresa")
        self.assertEqual(request.get_header("Authorization"), "Bearer admintoken")

    @patch("uoe_client.urllib.request.urlopen")
    def test_handles_an_empty_response_body(self, mock_urlopen):
        response = MagicMock()
        response.read.return_value = b""
        response.__enter__.return_value = response
        mock_urlopen.return_value = response
        self.assertIsNone(uoe_client.delete_user("admintoken", "empresa"))


if __name__ == "__main__":
    unittest.main()
