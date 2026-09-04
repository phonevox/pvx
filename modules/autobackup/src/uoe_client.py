import json
import urllib.error
import urllib.request

BASE_URL = "http://uoe.interno.falevox.com.br/v1"


class UOEError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"UOE respondeu {status}: {body}")


def _request(method, path, payload=None, token=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        raise UOEError(e.code, e.read().decode(errors="replace"))
    except urllib.error.URLError as e:
        raise UOEError(None, str(e.reason))


def login(username, password):
    result = _request("POST", "/users/login", {"username": username, "password": password})
    return result["token"]


def register(admin_token, username, password, root_path, role="user"):
    return _request(
        "POST", "/users/register",
        {"username": username, "password": password, "role": role, "root_path": root_path},
        token=admin_token,
    )


def delete_user(admin_token, username):
    return _request("DELETE", f"/users/{username}", token=admin_token)
