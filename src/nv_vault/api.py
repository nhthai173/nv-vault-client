from __future__ import annotations

import json
import urllib.error
import urllib.request
from importlib.metadata import PackageNotFoundError, version


class ApiError(Exception):
    pass


def _client_version() -> str:
    try:
        return version("nv-vault")
    except PackageNotFoundError:   # run from a source tree that is not installed
        return "dev"


# sent with every request, so the server can tell which client version is calling
USER_AGENT = f"nv-vault/{_client_version()}"


def call(base: str, version: str, token: str, method: str, path: str, body: dict | None = None,
         timeout: float = 30) -> dict:
    url = f"{base}/api/{version}{path}"  # every path lives under /api/<version>, healthz included
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            d = json.load(e).get("detail")
        except ValueError:
            d = None
        msg = d.get("reason") if isinstance(d, dict) else d
        raise ApiError(f"{e.code} {msg or e.reason}") from None
    except urllib.error.URLError as e:
        raise ApiError(f"cannot reach {base}: {e.reason}") from None
    except TimeoutError:
        raise ApiError(f"timed out after {timeout:g}s: {base}") from None
