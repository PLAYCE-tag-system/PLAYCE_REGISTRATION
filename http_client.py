import json
import urllib.error
import urllib.request


def post_json(base_url, path, payload):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return request_json(request)


def get_json(base_url, path):
    request = urllib.request.Request(f"{base_url}{path}", method="GET")
    return request_json(request)


def delete_json(base_url, path):
    request = urllib.request.Request(f"{base_url}{path}", method="DELETE")
    return request_json(request)


def request_json(request):
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{error.code} {message}") from error
