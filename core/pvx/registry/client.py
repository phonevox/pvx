import json
import urllib.request


def fetch_index(url):
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read())
