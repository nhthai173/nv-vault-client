from __future__ import annotations

import json
import urllib.error
import urllib.request


class ApiError(Exception):
    pass


def call(base: str, version: str, token: str, method: str, path: str, body: dict | None = None,
         timeout: float = 30, versioned: bool = True) -> dict:
    url = f"{base}/{version}{path}" if versioned else f"{base}{path}"
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
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
